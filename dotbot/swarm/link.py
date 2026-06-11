# SPDX-FileCopyrightText: 2026-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Link-budget value types.

`swarm.link` returns a `LinkProfile`: a snapshot of the active link and its
per-gateway packet budget (SDK plan sections 3 and 5). The shape is generic on
purpose - the Mari link fills it from marilib `GatewayInfo`, but a wifi or
direct-BLE link would fill the same fields. `LinkProfile.bottleneck` is the
"common link denominator": the most-saturated gateway, so a swarm-wide control
loop can pace itself to the slowest one.

NOTE (SDK plan section 5, flagged-undecided): `GatewayBudget` / `.gateways` lean
on Mari's "gateway" word inside an otherwise link-agnostic profile. A neutral
term (`segment`, with Mari mapping gateway -> segment) is still under
consideration; kept as `gateways` here to match the plan's primary text.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GatewayBudget:
    """The packet budget of a single gateway (one Mari network / schedule).

    All rates are per second. `per_bot_command_rate_hz` is the downlink budget
    divided by the bots currently on this gateway, so it shrinks as the gateway
    fills (this is the number the SDK paces unicast commands against).
    `queue_depth` is the live backpressure signal (slotframes of backlog), set
    only when the backend can read it directly (a `mqtts://` / serial
    connection); it stays None over an HTTP connection unless the controller
    chooses to expose it.
    """

    max_bots: int
    downlink_rate_hz: float
    uplink_rate_hz: float
    per_bot_command_rate_hz: float
    address: str | None = None
    bots: int | None = None
    queue_depth: float | None = None

    @classmethod
    def from_dict(cls, d: dict) -> GatewayBudget:
        """Build from the JSON the `GET /controller/link` endpoint returns."""
        return cls(
            max_bots=int(d["max_bots"]),
            downlink_rate_hz=float(d["downlink_rate_hz"]),
            uplink_rate_hz=float(d["uplink_rate_hz"]),
            per_bot_command_rate_hz=float(d["per_bot_command_rate_hz"]),
            address=d.get("address"),
            bots=d.get("bots"),
            queue_depth=d.get("queue_depth"),
        )


@dataclass(frozen=True, slots=True)
class LinkProfile:
    """A snapshot of the active link and its per-gateway budget.

    `kind` is "mari" | "wifi" | "ble-direct" | ...; `position_rate_hz` is the
    host-side position report rate (~2 Hz on Mari, via the DotBot
    advertisement). Mari scales horizontally, so the budget is per gateway and
    `gateways` may hold several entries; a single-bot BLE link reports one.
    """

    kind: str
    position_rate_hz: float
    gateways: tuple[GatewayBudget, ...] = ()

    @property
    def bottleneck(self) -> GatewayBudget | None:
        """The most-saturated gateway - the common denominator a swarm-wide loop
        should pace to. Prefers live queue depth when any gateway reports it,
        otherwise the gateway with the lowest per-bot command rate. None when
        there are no gateways.
        """
        if not self.gateways:
            return None
        if any(g.queue_depth is not None for g in self.gateways):
            return max(
                self.gateways,
                key=lambda g: g.queue_depth if g.queue_depth is not None else -1.0,
            )
        return min(self.gateways, key=lambda g: g.per_bot_command_rate_hz)

    @classmethod
    def from_dict(cls, d: dict) -> LinkProfile:
        """Build from the JSON the `GET /controller/link` endpoint returns."""
        return cls(
            kind=str(d.get("kind", "unknown")),
            position_rate_hz=float(d.get("position_rate_hz", 0.0)),
            gateways=tuple(GatewayBudget.from_dict(g) for g in d.get("gateways", ())),
        )

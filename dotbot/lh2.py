# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""LH2 base station channels and the DotBot station index each decodes to."""

LH2_BASESTATION_COUNT_MAX = 16
CHANNELS = range(1, LH2_BASESTATION_COUNT_MAX + 1)


def channel_index(channel: int) -> int:
    """The station index a channel's sweeps decode to."""
    return channel - 1


def station_label(index: int) -> str:
    """How a station is named to an operator: its index and its channel."""
    return f"station {index} (channel {index + 1})"

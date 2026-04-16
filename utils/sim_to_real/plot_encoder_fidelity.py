# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-FileCopyrightText: 2026-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Plot encoder fidelity vs. real robot data (AUTO mode only).

Metrics shown
-------------
- Real vs. sim encoder counts over time (left and right wheels)
- Per-step encoder residual (real - sim) over time
- Left/right residual distribution (box plot)
- Cumulative encoder counts over time
"""

from pathlib import Path

import click
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_auto(csv_path: Path, address: str | None) -> dict[str, pd.DataFrame]:
    """Return a dict {address: DataFrame} with only AUTO-mode rows."""
    df = pd.read_csv(csv_path)

    required = {
        "timestamp",
        "encoder_left",
        "encoder_right",
        "sim_encoder_left",
        "sim_encoder_right",
        "control_mode",
        "address",
    }
    missing = required - set(df.columns)
    if missing:
        console.print(f"[bold red]Error:[/bold red] CSV missing columns: {missing}")
        raise SystemExit(1)

    df = df[df["control_mode"] == "AUTO"].copy()
    if df.empty:
        console.print("[bold red]Error:[/bold red] no AUTO-mode rows found.")
        raise SystemExit(1)

    if address is not None:
        df = df[df["address"] == address]
        if df.empty:
            console.print(
                f"[bold red]Error:[/bold red] no AUTO rows for address '{address}'."
            )
            raise SystemExit(1)

    return {addr: grp.reset_index(drop=True) for addr, grp in df.groupby("address")}


def residuals(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    left = df["encoder_left"].to_numpy() - df["sim_encoder_left"].to_numpy()
    right = df["encoder_right"].to_numpy() - df["sim_encoder_right"].to_numpy()
    return left, right


# ---------------------------------------------------------------------------
# Plot functions
# ---------------------------------------------------------------------------


def plot_counts(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Real vs. sim per-step encoder counts over time."""
    t = df["timestamp"].to_numpy() - df["timestamp"].iloc[0]
    ax.plot(t, df["encoder_left"], color="steelblue", linewidth=1.2, label="real left")
    ax.plot(
        t,
        df["sim_encoder_left"],
        color="steelblue",
        linewidth=1.2,
        linestyle="--",
        label="sim left",
    )
    ax.plot(
        t, df["encoder_right"], color="darkorange", linewidth=1.2, label="real right"
    )
    ax.plot(
        t,
        df["sim_encoder_right"],
        color="darkorange",
        linewidth=1.2,
        linestyle="--",
        label="sim right",
    )
    ax.set_xlabel("time [s]")
    ax.set_ylabel("encoder counts / step")
    ax.set_title(f"Encoder counts — {address}")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.4)


def plot_residual(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Per-step residual (real - sim) over time."""
    t = df["timestamp"].to_numpy() - df["timestamp"].iloc[0]
    res_l, res_r = residuals(df)
    ax.plot(t, res_l, color="steelblue", linewidth=1.2, label="left")
    ax.plot(t, res_r, color="darkorange", linewidth=1.2, label="right")
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("residual [counts]")
    ax.set_title(f"Encoder residual (real − sim) — {address}")
    ax.legend()
    ax.grid(True, alpha=0.4)


def plot_residual_dist(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Box plot of left/right residuals."""
    res_l, res_r = residuals(df)
    ax.boxplot(
        [res_l, res_r],
        labels=["left", "right"],
        patch_artist=True,
        boxprops=dict(facecolor="steelblue", alpha=0.5),
    )
    ax.axhline(0, color="gray", linewidth=0.8)
    ax.set_ylabel("residual [counts]")
    ax.set_title(f"Residual distribution — {address}")
    ax.grid(True, axis="y", alpha=0.4)


def plot_cumulative(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Cumulative encoder counts over time."""
    t = df["timestamp"].to_numpy() - df["timestamp"].iloc[0]
    ax.plot(
        t,
        df["encoder_left"].cumsum(),
        color="steelblue",
        linewidth=1.2,
        label="real left",
    )
    ax.plot(
        t,
        df["sim_encoder_left"].cumsum(),
        color="steelblue",
        linewidth=1.2,
        linestyle="--",
        label="sim left",
    )
    ax.plot(
        t,
        df["encoder_right"].cumsum(),
        color="darkorange",
        linewidth=1.2,
        label="real right",
    )
    ax.plot(
        t,
        df["sim_encoder_right"].cumsum(),
        color="darkorange",
        linewidth=1.2,
        linestyle="--",
        label="sim right",
    )
    ax.set_xlabel("time [s]")
    ax.set_ylabel("cumulative counts")
    ax.set_title(f"Cumulative encoder counts — {address}")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.4)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("csv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--address",
    "-a",
    default=None,
    help="Filter to a specific robot address (default: all robots).",
)
@click.option(
    "--save",
    "-s",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory to save PNG figures (default: show interactively).",
)
def main(csv, address, save):
    """Plot encoder fidelity metrics (AUTO mode only)."""
    if save is not None:
        save.mkdir(parents=True, exist_ok=True)

    console.print(Panel(f"[bold]Loading[/bold] {csv}", expand=False))
    robots = load_auto(csv, address)

    summary = Table(
        "Address",
        "AUTO rows",
        "Mean |res left|",
        "Mean |res right|",
        header_style="bold cyan",
    )
    for addr, df in robots.items():
        res_l, res_r = residuals(df)
        summary.add_row(
            addr,
            str(len(df)),
            f"{np.abs(res_l).mean():.2f}",
            f"{np.abs(res_r).mean():.2f}",
        )
    console.print(summary)

    for addr, df in robots.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        res_l, res_r = residuals(df)
        fig.suptitle(
            f"Encoder fidelity — {addr}\n"
            f"({len(df)} samples, mean |residual| left={np.abs(res_l).mean():.2f} "
            f"right={np.abs(res_r).mean():.2f})",
            fontsize=13,
        )
        plot_counts(axes[0, 0], df, addr)
        plot_residual(axes[0, 1], df, addr)
        plot_cumulative(axes[1, 0], df, addr)
        plot_residual_dist(axes[1, 1], df, addr)
        fig.tight_layout()

        if save is not None:
            out = save / f"encoder_fidelity_{addr}.png"
            fig.savefig(out, dpi=150)
            console.print(f"  [green]Saved[/green] {out}")
        else:
            plt.show()


if __name__ == "__main__":
    main()

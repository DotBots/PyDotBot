# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-FileCopyrightText: 2026-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Plot simulation fidelity vs. real robot data (AUTO mode only).

Metrics shown
-------------
- XY trajectory overlay (real vs. sim) per robot per waypoint segment
- Position RMSE  √(Δx² + Δy²)  over time
- Time-to-reach-goal comparison per waypoint
- Per-waypoint RMSE box plot
"""

from pathlib import Path

import click
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
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
        "real_pos_x",
        "real_pos_y",
        "sim_pos_x",
        "sim_pos_y",
        "control_mode",
        "waypoint_index",
        "waypoint_x",
        "waypoint_y",
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


def rmse_position(df: pd.DataFrame) -> np.ndarray:
    dx = df["real_pos_x"].to_numpy() - df["sim_pos_x"].to_numpy()
    dy = df["real_pos_y"].to_numpy() - df["sim_pos_y"].to_numpy()
    return np.sqrt(dx**2 + dy**2)


def time_to_reach(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with columns [waypoint_index, real_t, sim_t] in seconds."""
    records = []
    t0 = df["timestamp"].iloc[0]
    dt = df["timestamp"].diff().median()
    for wp_idx, grp in df.groupby("waypoint_index", sort=True):
        real_t = grp["timestamp"].iloc[-1] - t0
        sim_t = len(grp) * dt
        records.append(
            {"waypoint_index": int(wp_idx), "real_t": real_t, "sim_t": sim_t}
        )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Plot functions
# ---------------------------------------------------------------------------


def plot_trajectory(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """XY trajectory overlay, coloured by waypoint segment."""
    cmap = plt.get_cmap("tab10")
    for i, wp in enumerate(sorted(df["waypoint_index"].unique())):
        seg = df[df["waypoint_index"] == wp]
        color = cmap(i % 10)
        ax.plot(seg["real_pos_x"], seg["real_pos_y"], color=color, linewidth=1.5)
        ax.plot(
            seg["sim_pos_x"],
            seg["sim_pos_y"],
            color=color,
            linewidth=1.5,
            linestyle="--",
        )
        ax.scatter(
            seg["waypoint_x"].iloc[0],
            seg["waypoint_y"].iloc[0],
            marker="x",
            s=80,
            color=color,
            zorder=5,
        )

    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title(f"Trajectory — {address}")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.4)
    ax.legend(
        handles=[
            Line2D([0], [0], color="gray", linewidth=1.5, label="real"),
            Line2D([0], [0], color="gray", linewidth=1.5, linestyle="--", label="sim"),
        ],
        loc="best",
    )


def plot_rmse(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Position RMSE √(Δx²+Δy²) over time."""
    t = df["timestamp"].to_numpy() - df["timestamp"].iloc[0]
    rmse = rmse_position(df)
    ax.plot(t, rmse, linewidth=1.2, color="steelblue")
    ax.fill_between(t, 0, rmse, alpha=0.2, color="steelblue")
    ax.axhline(
        rmse.mean(), color="tomato", linestyle="--", label=f"mean {rmse.mean():.1f} mm"
    )
    ax.set_xlabel("time [s]")
    ax.set_ylabel("RMSE [mm]")
    ax.set_title(f"Position RMSE — {address}")
    ax.legend()
    ax.grid(True, alpha=0.4)
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator())


def plot_time_to_reach(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Bar chart comparing real vs. sim time to reach each waypoint."""
    ttr = time_to_reach(df)
    if ttr.empty:
        ax.set_visible(False)
        return
    x = np.arange(len(ttr))
    width = 0.35
    ax.bar(x - width / 2, ttr["real_t"], width, label="real", color="steelblue")
    ax.bar(
        x + width / 2, ttr["sim_t"], width, label="sim", color="darkorange", alpha=0.8
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"wp{int(r)}" for r in ttr["waypoint_index"]])
    ax.set_xlabel("Waypoint")
    ax.set_ylabel("Time to reach [s]")
    ax.set_title(f"Time to reach goal — {address}")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.4)


def plot_rmse_per_waypoint(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Box plot of per-waypoint RMSE distribution."""
    groups = {
        f"wp{int(wp_idx)}": rmse_position(grp)
        for wp_idx, grp in df.groupby("waypoint_index", sort=True)
    }
    if not groups:
        ax.set_visible(False)
        return
    ax.boxplot(
        groups.values(),
        labels=groups.keys(),
        patch_artist=True,
        boxprops=dict(facecolor="steelblue", alpha=0.5),
    )
    ax.set_xlabel("Waypoint")
    ax.set_ylabel("RMSE [mm]")
    ax.set_title(f"RMSE per waypoint — {address}")
    ax.grid(True, axis="y", alpha=0.4)


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
    """Plot simulation fidelity metrics (AUTO mode only)."""
    if save is not None:
        save.mkdir(parents=True, exist_ok=True)

    console.print(Panel(f"[bold]Loading[/bold] {csv}", expand=False))
    robots = load_auto(csv, address)

    summary = Table("Address", "AUTO rows", "Mean RMSE", header_style="bold cyan")
    for addr, df in robots.items():
        summary.add_row(addr, str(len(df)), f"{rmse_position(df).mean():.1f} mm")
    console.print(summary)

    for addr, df in robots.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"Simulation fidelity — {addr}\n"
            f"({len(df)} samples, overall RMSE {rmse_position(df).mean():.1f} mm mean)",
            fontsize=13,
        )
        plot_trajectory(axes[0, 0], df, addr)
        plot_rmse(axes[0, 1], df, addr)
        plot_time_to_reach(axes[1, 0], df, addr)
        plot_rmse_per_waypoint(axes[1, 1], df, addr)
        fig.tight_layout()

        if save is not None:
            out = save / f"fidelity_{addr}.png"
            fig.savefig(out, dpi=150)
            console.print(f"  [green]Saved[/green] {out}")
        else:
            plt.show()


if __name__ == "__main__":
    main()

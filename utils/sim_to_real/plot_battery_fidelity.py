# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-FileCopyrightText: 2026-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Plot simulated vs. real battery voltage fidelity.

Plots produced
--------------
- Voltage over time: real and simulated battery voltage on the same axes
- Absolute error over time: |real − sim|
- Error distribution: histogram of the absolute error
- Voltage vs. PWM: scatter of battery voltage coloured by mean PWM level
"""

from pathlib import Path

import click
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

REQUIRED_COLS = {
    "timestamp",
    "battery_level",
    "sim_battery_voltage",
    "pwm_left",
    "pwm_right",
    "address",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load(csv_path: Path, address: str | None) -> dict[str, pd.DataFrame]:
    """Return a dict {address: DataFrame} filtered to rows with valid battery data."""
    df = pd.read_csv(csv_path)

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        console.print(f"[bold red]Error:[/bold red] CSV missing columns: {missing}")
        raise SystemExit(1)

    df = df.dropna(subset=["battery_level", "sim_battery_voltage"]).copy()
    if df.empty:
        console.print("[bold red]Error:[/bold red] no rows with battery data found.")
        raise SystemExit(1)

    if address is not None:
        df = df[df["address"] == address]
        if df.empty:
            console.print(
                f"[bold red]Error:[/bold red] no rows for address '{address}'."
            )
            raise SystemExit(1)

    return {addr: grp.reset_index(drop=True) for addr, grp in df.groupby("address")}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def abs_error(df: pd.DataFrame) -> np.ndarray:
    return np.abs(df["battery_level"].to_numpy() - df["sim_battery_voltage"].to_numpy())


# ---------------------------------------------------------------------------
# Plot functions
# ---------------------------------------------------------------------------


def plot_voltage_over_time(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Real and simulated voltage on the same axes."""
    t = df["timestamp"].to_numpy() - df["timestamp"].iloc[0]
    ax.plot(t, df["battery_level"], label="real", color="steelblue", linewidth=1.5)
    ax.plot(
        t,
        df["sim_battery_voltage"],
        label="sim",
        color="darkorange",
        linewidth=1.5,
        linestyle="--",
    )
    ax.set_xlabel("time [s]")
    ax.set_ylabel("voltage [V]")
    ax.set_title(f"Battery voltage — {address}")
    ax.legend()
    ax.grid(True, alpha=0.4)
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator())


def plot_error_over_time(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Absolute voltage error |real − sim| over time."""
    t = df["timestamp"].to_numpy() - df["timestamp"].iloc[0]
    err = abs_error(df)
    ax.plot(t, err, color="tomato", linewidth=1.2)
    ax.fill_between(t, 0, err, alpha=0.2, color="tomato")
    ax.axhline(
        err.mean(),
        color="steelblue",
        linestyle="--",
        label=f"mean {err.mean():.4f} V",
    )
    ax.set_xlabel("time [s]")
    ax.set_ylabel("|real − sim| [V]")
    ax.set_title(f"Absolute voltage error — {address}")
    ax.legend()
    ax.grid(True, alpha=0.4)
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator())


def plot_error_distribution(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Histogram of absolute voltage error."""
    err = abs_error(df)
    ax.hist(err, bins=40, color="steelblue", alpha=0.75, edgecolor="white")
    ax.axvline(
        err.mean(), color="tomato", linestyle="--", label=f"mean {err.mean():.4f} V"
    )
    ax.axvline(
        np.median(err),
        color="darkorange",
        linestyle=":",
        label=f"median {np.median(err):.4f} V",
    )
    ax.set_xlabel("|real − sim| [V]")
    ax.set_ylabel("count")
    ax.set_title(f"Error distribution — {address}")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.4)


def plot_voltage_vs_pwm(ax: plt.Axes, df: pd.DataFrame, address: str) -> None:
    """Real vs. sim voltage scatter, coloured by mean PWM magnitude."""
    mean_pwm = (df["pwm_left"].abs() + df["pwm_right"].abs()) / 2.0
    sc = ax.scatter(
        df["battery_level"],
        df["sim_battery_voltage"],
        c=mean_pwm,
        cmap="viridis",
        s=8,
        alpha=0.6,
    )
    vmin = min(df["battery_level"].min(), df["sim_battery_voltage"].min())
    vmax = max(df["battery_level"].max(), df["sim_battery_voltage"].max())
    ax.plot(
        [vmin, vmax],
        [vmin, vmax],
        color="tomato",
        linestyle="--",
        linewidth=1,
        label="ideal",
    )
    plt.colorbar(sc, ax=ax, label="mean |PWM|")
    ax.set_xlabel("real voltage [V]")
    ax.set_ylabel("sim voltage [V]")
    ax.set_title(f"Real vs. sim voltage — {address}")
    ax.legend()
    ax.grid(True, alpha=0.4)
    ax.set_aspect("equal")


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
    """Plot simulated vs. real battery voltage fidelity."""
    if save is not None:
        save.mkdir(parents=True, exist_ok=True)

    console.print(Panel(f"[bold]Loading[/bold] {csv}", expand=False))
    robots = load(csv, address)

    summary = Table(
        "Address",
        "Rows",
        "Mean |error| [V]",
        "Max |error| [V]",
        header_style="bold cyan",
    )
    for addr, df in robots.items():
        err = abs_error(df)
        summary.add_row(
            addr,
            str(len(df)),
            f"{err.mean():.4f}",
            f"{err.max():.4f}",
        )
    console.print(summary)

    for addr, df in robots.items():
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(
            f"Battery fidelity — {addr}\n"
            f"({len(df)} samples, mean |error| {abs_error(df).mean():.4f} V)",
            fontsize=13,
        )
        plot_voltage_over_time(axes[0, 0], df, addr)
        plot_error_over_time(axes[0, 1], df, addr)
        plot_error_distribution(axes[1, 0], df, addr)
        plot_voltage_vs_pwm(axes[1, 1], df, addr)
        fig.tight_layout()

        if save is not None:
            out = save / f"battery_fidelity_{addr}.png"
            fig.savefig(out, dpi=150)
            console.print(f"  [green]Saved[/green] {out}")
        else:
            plt.show()


if __name__ == "__main__":
    main()

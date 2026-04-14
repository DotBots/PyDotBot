# SPDX-FileCopyrightText: 2024-present Inria
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Train a battery discharge model for the DotBot simulator.

The model learns to predict the instantaneous battery discharge rate (mV/s)
from motor PWM commands and encoder readings. During simulation, the predicted
rate is integrated over time to update the battery voltage, replacing the
purely time-based discharge model.

Two model architectures are available:
  linear  — linear regression (interpretable, fast)
  mlp     — small multi-layer perceptron (captures non-linearities)

Both are exported as TorchScript so they can be loaded by the simulator
without the training code present. The path to the saved model is then
referenced in simulator_init_state.toml via ``battery_model_path``.
"""

from pathlib import Path

import click
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from torch.utils.data import DataLoader, TensorDataset

console = Console()

# ---------------------------------------------------------------------------
# Features and target
# ---------------------------------------------------------------------------

FEATURE_COLS = ["pwm_left", "pwm_right", "encoder_left", "encoder_right"]

# Maximum delta_t between consecutive rows of the same robot to be considered
# part of the same session (larger gaps indicate a controller restart).
MAX_DELTA_T_S = 2.0

# battery_level in the CSV is in Volts; convert to mV to match the simulator.
BATTERY_MV_SCALE = 1000.0


# ---------------------------------------------------------------------------
# Data loading and preprocessing
# ---------------------------------------------------------------------------


def load_and_prepare(csv_path: Path) -> pd.DataFrame:
    """Load CSV and compute per-step discharge rate (mV/s) for each robot."""
    df = pd.read_csv(csv_path)

    required = set(
        FEATURE_COLS + ["timestamp", "battery_level", "address", "control_mode"]
    )
    missing = required - set(df.columns)
    if missing:
        console.print(f"[bold red]Error:[/bold red] CSV is missing columns: {missing}")
        raise SystemExit(1)

    # Convert battery voltage from V to mV
    df["battery_mv"] = df["battery_level"] * BATTERY_MV_SCALE

    rows = []
    for address, group in df.groupby("address"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        delta_t = group["timestamp"].diff()
        delta_mv = group["battery_mv"].diff()

        # Discharge rate in mV/s (negative = discharging)
        rate = delta_mv / delta_t

        mask = (
            (delta_t > 0)
            & (delta_t < MAX_DELTA_T_S)
            & (rate <= 0)  # only keep discharge samples (drop noise/charging)
        )

        subset = group[mask].copy()
        subset["discharge_rate"] = rate[mask].values
        rows.append(subset)

    if not rows:
        console.print(
            "[bold red]Error:[/bold red] No valid discharge samples found in the CSV."
        )
        raise SystemExit(1)

    result = pd.concat(rows, ignore_index=True)
    return result


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LinearBatteryModel(nn.Module):
    """Linear regression: discharge_rate = w · features + b."""

    def __init__(self, n_features: int):
        super().__init__()
        self.linear = nn.Linear(n_features, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.linear(x)  # (batch, 1)


class MLPBatteryModel(nn.Module):
    """Small MLP for battery discharge rate prediction."""

    def __init__(self, n_features: int, hidden_size: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Linear(hidden_size // 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)  # (batch, 1)


# ---------------------------------------------------------------------------
# Normalisation wrapper (baked-in, TorchScript-compatible)
# ---------------------------------------------------------------------------


class NormalisedBatteryModel(nn.Module):
    """Wraps a battery model with input/output normalisation baked in.

    forward(x) accepts raw (un-normalised) feature values and returns the
    predicted discharge rate in mV/s.
    """

    def __init__(
        self,
        core: nn.Module,
        feat_mean: np.ndarray,
        feat_std: np.ndarray,
        rate_mean: float,
        rate_std: float,
    ):
        super().__init__()
        self.core = core
        self.register_buffer("feat_mean", torch.from_numpy(feat_mean))
        self.register_buffer("feat_std", torch.from_numpy(feat_std))
        self.register_buffer("rate_mean", torch.tensor(rate_mean, dtype=torch.float32))
        self.register_buffer("rate_std", torch.tensor(rate_std, dtype=torch.float32))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (1, n_features) raw values → scalar discharge rate (mV/s)."""
        x_norm = (x - self.feat_mean) / self.feat_std
        y_norm = self.core(x_norm)  # (1, 1)
        return y_norm * self.rate_std + self.rate_mean  # (1, 1)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(
    csv_path: Path,
    output_path: Path,
    model_type: str,
    epochs: int,
    hidden_size: int,
    batch_size: int,
    lr: float,
):
    if not csv_path.exists():
        console.print(f"[bold red]Error:[/bold red] CSV file not found: {csv_path}")
        raise SystemExit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(Panel(f"[bold]Loading[/bold] {csv_path}", expand=False))
    df = load_and_prepare(csv_path)

    summary = Table(show_header=False, box=None, padding=(0, 1))
    summary.add_row("[cyan]Samples[/cyan]", str(len(df)))
    summary.add_row("[cyan]Robots[/cyan]", str(df["address"].nunique()))
    summary.add_row("[cyan]Addresses[/cyan]", ", ".join(df["address"].unique()))
    summary.add_row(
        "[cyan]Discharge rate (mV/s)[/cyan]",
        f"min={df['discharge_rate'].min():.3f}  "
        f"mean={df['discharge_rate'].mean():.3f}  "
        f"max={df['discharge_rate'].max():.3f}",
    )
    console.print(summary)

    # Normalisation statistics (computed on training data only, but we use the
    # full dataset here since the CSV is typically from a single collection run)
    feat_mean = df[FEATURE_COLS].mean().to_numpy(dtype=np.float32)
    feat_std = df[FEATURE_COLS].std().to_numpy(dtype=np.float32)
    feat_std[feat_std < 1e-6] = 1.0

    rate_mean = float(df["discharge_rate"].mean())
    rate_std = float(df["discharge_rate"].std())
    if rate_std < 1e-6:
        rate_std = 1.0

    X = torch.from_numpy(
        ((df[FEATURE_COLS].to_numpy(dtype=np.float32) - feat_mean) / feat_std)
    )
    y = torch.from_numpy(
        ((df["discharge_rate"].to_numpy(dtype=np.float32) - rate_mean) / rate_std)
    ).unsqueeze(1)

    val_size = max(1, int(0.2 * len(X)))
    train_size = len(X) - val_size
    indices = torch.randperm(len(X))
    train_idx, val_idx = indices[:train_size], indices[train_size:]

    train_loader = DataLoader(
        TensorDataset(X[train_idx], y[train_idx]),
        batch_size=batch_size,
        shuffle=True,
    )
    val_loader = DataLoader(
        TensorDataset(X[val_idx], y[val_idx]),
        batch_size=batch_size,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    console.print(
        f"\n  Model: [bold magenta]{model_type}[/bold magenta]  |  "
        f"Device: [bold magenta]{device}[/bold magenta]\n"
    )

    n_features = len(FEATURE_COLS)
    if model_type == "linear":
        core = LinearBatteryModel(n_features).to(device)
    else:
        core = MLPBatteryModel(n_features, hidden_size).to(device)

    optimiser = torch.optim.Adam(core.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimiser, patience=5, factor=0.5
    )
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None

    epoch_table = Table(
        "Epoch",
        "Train loss",
        "Val loss",
        "Best",
        box=None,
        header_style="bold cyan",
    )

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Training…", total=epochs)

        for epoch in range(1, epochs + 1):
            core.train()
            train_loss = 0.0
            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                optimiser.zero_grad()
                loss = criterion(core(xb), yb)
                loss.backward()
                optimiser.step()
                train_loss += loss.item() * len(xb)
            train_loss /= train_size

            core.eval()
            val_loss = 0.0
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb, yb = xb.to(device), yb.to(device)
                    val_loss += criterion(core(xb), yb).item() * len(xb)
            val_loss /= val_size
            scheduler.step(val_loss)

            is_best = val_loss < best_val_loss
            if is_best:
                best_val_loss = val_loss
                best_state = {k: v.cpu().clone() for k, v in core.state_dict().items()}

            progress.advance(task)

            if epoch % 10 == 0 or epoch == 1:
                epoch_table.add_row(
                    f"{epoch}/{epochs}",
                    f"{train_loss:.6f}",
                    f"{val_loss:.6f}",
                    "[green]✓[/green]" if is_best else "",
                )

    console.print(epoch_table)

    core.load_state_dict(best_state)
    core.eval().cpu()

    wrapped = NormalisedBatteryModel(core, feat_mean, feat_std, rate_mean, rate_std)
    scripted = torch.jit.script(wrapped)
    scripted.save(str(output_path))

    console.print(
        Panel(
            f"[green]Model saved to[/green] {output_path.resolve()}\n"
            f"[green]Best validation loss:[/green] {best_val_loss:.6f}\n\n"
            f"Add to [bold]simulator_init_state.toml[/bold]:\n"
            f'  [yellow]battery_model_path[/yellow] = "{output_path.resolve()}"',
            title="Done",
            expand=False,
        )
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("csv", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=Path("models/battery_model.pt"),
    show_default=True,
    help="Output path for the TorchScript model.",
)
@click.option(
    "--model",
    "-m",
    type=click.Choice(["linear", "mlp"]),
    default="mlp",
    show_default=True,
    help="Model architecture.",
)
@click.option(
    "--epochs",
    type=int,
    default=100,
    show_default=True,
    help="Number of training epochs.",
)
@click.option(
    "--hidden-size",
    type=int,
    default=64,
    show_default=True,
    help="MLP hidden layer size (ignored for linear).",
)
@click.option(
    "--batch-size", type=int, default=64, show_default=True, help="Training batch size."
)
@click.option(
    "--lr", type=float, default=1e-3, show_default=True, help="Adam learning rate."
)
def main(csv, output, model, epochs, hidden_size, batch_size, lr):
    """Train a battery discharge model for the DotBot simulator."""
    train(csv, output, model, epochs, hidden_size, batch_size, lr)


if __name__ == "__main__":
    main()

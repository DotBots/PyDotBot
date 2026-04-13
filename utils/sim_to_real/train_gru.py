# SPDX-FileCopyrightText: 2024-present Inria
# SPDX-FileCopyrightText: 2024-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Train a GRU model to reduce the sim-to-real gap in DotBot position prediction.

The model learns to predict the residual error between the kinematic simulator
output (sim_pos_x, sim_pos_y) and the real robot position (real_pos_x,
real_pos_y). During inference in the simulator, the predicted residual is added
on top of the kinematic step at each SIMULATOR_UPDATE_INTERVAL_S tick.

The model is saved as a TorchScript file so it can be loaded without the
training code present. The path to the saved model is then referenced in
simulator_init_state.toml via ``gru_model_path``.
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
from torch.utils.data import DataLoader, Dataset

console = Console()

# ---------------------------------------------------------------------------
# Features fed to the GRU at every timestep
# ---------------------------------------------------------------------------
FEATURE_COLS = [
    "pwm_left",
    "pwm_right",
    "encoder_left",
    "encoder_right",
    "real_direction",
    "sim_pos_x",
    "sim_pos_y",
]
TARGET_COLS = ["residual_x", "residual_y"]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


class ResidualSequenceDataset(Dataset):
    """Sliding-window dataset over per-robot AUTO-mode sequences."""

    def __init__(
        self,
        df: pd.DataFrame,
        seq_len: int,
        feature_cols: list[str],
        target_cols: list[str],
    ):
        self.seq_len = seq_len
        self.sequences: list[tuple[np.ndarray, np.ndarray]] = []

        for address, group in df.groupby("address"):
            auto = group[group["control_mode"] == "AUTO"].copy()
            if len(auto) < seq_len + 1:
                console.print(
                    f"  [yellow]Skipping {address}:[/yellow] only {len(auto)} AUTO rows "
                    f"(need >{seq_len})"
                )
                continue

            X = auto[feature_cols].to_numpy(dtype=np.float32)
            Y = auto[target_cols].to_numpy(dtype=np.float32)

            for start in range(len(auto) - seq_len):
                self.sequences.append(
                    (X[start : start + seq_len], Y[start + seq_len - 1])
                )

    def __len__(self):
        return len(self.sequences)

    def __getitem__(self, idx):
        x, y = self.sequences[idx]
        return torch.from_numpy(x), torch.from_numpy(y)


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class ResidualGRU(nn.Module):
    """GRU that predicts (dx_residual, dy_residual) from a state sequence."""

    def __init__(self, input_size: int, hidden_size: int, num_layers: int = 2):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.1 if num_layers > 1 else 0.0,
        )
        self.head = nn.Linear(hidden_size, 2)  # (residual_x, residual_y)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, input_size)
        out, _ = self.gru(x)
        return self.head(out[:, -1, :])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_and_prepare(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    required = set(
        FEATURE_COLS
        + [
            "real_pos_x",
            "real_pos_y",
            "sim_pos_x",
            "sim_pos_y",
            "control_mode",
            "address",
        ]
    )
    missing = required - set(df.columns)
    if missing:
        console.print(f"[bold red]Error:[/bold red] CSV is missing columns: {missing}")
        raise SystemExit(1)

    df["residual_x"] = df["real_pos_x"] - df["sim_pos_x"]
    df["residual_y"] = df["real_pos_y"] - df["sim_pos_y"]
    return df


def compute_normalisation(
    df: pd.DataFrame, cols: list[str]
) -> tuple[np.ndarray, np.ndarray]:
    mean = df[cols].mean().to_numpy(dtype=np.float32)
    std = df[cols].std().to_numpy(dtype=np.float32)
    std[std < 1e-6] = 1.0  # avoid division by zero for constant features
    return mean, std


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def train(
    csv_path, output_path, epochs, seq_len, hidden_size, num_layers, batch_size, lr
):
    if not csv_path.exists():
        console.print(f"[bold red]Error:[/bold red] CSV file not found: {csv_path}")
        raise SystemExit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    console.print(Panel(f"[bold]Loading[/bold] {csv_path}", expand=False))
    df = load_and_prepare(csv_path)

    auto_df = df[df["control_mode"] == "AUTO"]
    if auto_df.empty:
        console.print("[bold red]Error:[/bold red] no AUTO-mode rows found in the CSV.")
        raise SystemExit(1)

    # Summary table
    summary = Table(show_header=False, box=None, padding=(0, 1))
    summary.add_row("[cyan]AUTO rows[/cyan]", str(len(auto_df)))
    summary.add_row("[cyan]Robots[/cyan]", str(auto_df["address"].nunique()))
    summary.add_row("[cyan]Addresses[/cyan]", ", ".join(auto_df["address"].unique()))
    console.print(summary)

    feat_mean, feat_std = compute_normalisation(auto_df, FEATURE_COLS)
    tgt_mean, tgt_std = compute_normalisation(auto_df, TARGET_COLS)

    df_norm = df.copy()
    df_norm[FEATURE_COLS] = (df[FEATURE_COLS] - feat_mean) / feat_std
    df_norm[TARGET_COLS] = (df[TARGET_COLS] - tgt_mean) / tgt_std

    dataset = ResidualSequenceDataset(
        df_norm,
        seq_len=seq_len,
        feature_cols=FEATURE_COLS,
        target_cols=TARGET_COLS,
    )
    console.print(f"  Total sequences: [bold]{len(dataset)}[/bold]")

    if len(dataset) == 0:
        console.print(
            "[bold red]Error:[/bold red] dataset is empty — not enough AUTO-mode data."
        )
        raise SystemExit(1)

    val_size = max(1, int(0.2 * len(dataset)))
    train_size = len(dataset) - val_size
    train_set, val_set = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=batch_size)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    console.print(f"  Training on [bold magenta]{device}[/bold magenta]\n")

    model = ResidualGRU(
        input_size=len(FEATURE_COLS),
        hidden_size=hidden_size,
        num_layers=num_layers,
    ).to(device)

    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimiser, patience=5, factor=0.5
    )
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None

    epoch_table = Table(
        "Epoch", "Train loss", "Val loss", "Best", box=None, header_style="bold cyan"
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
            model.train()
            train_loss = 0.0
            for xb, yb in train_loader:
                xb, yb = xb.to(device), yb.to(device)
                optimiser.zero_grad()
                pred = model(xb)
                loss = criterion(pred, yb)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                optimiser.step()
                train_loss += loss.item() * len(xb)
            train_loss /= train_size

            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for xb, yb in val_loader:
                    xb, yb = xb.to(device), yb.to(device)
                    val_loss += criterion(model(xb), yb).item() * len(xb)
            val_loss /= val_size
            scheduler.step(val_loss)

            is_best = val_loss < best_val_loss
            if is_best:
                best_val_loss = val_loss
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

            progress.advance(task)

            if epoch % 10 == 0 or epoch == 1:
                epoch_table.add_row(
                    f"{epoch}/{epochs}",
                    f"{train_loss:.6f}",
                    f"{val_loss:.6f}",
                    "[green]✓[/green]" if is_best else "",
                )

    console.print(epoch_table)

    # Restore best weights
    model.load_state_dict(best_state)
    model.eval().cpu()

    class NormalisedGRU(nn.Module):
        def __init__(self, core, feat_mean, feat_std, tgt_mean, tgt_std):
            super().__init__()
            self.core = core
            self.register_buffer("feat_mean", torch.from_numpy(feat_mean))
            self.register_buffer("feat_std", torch.from_numpy(feat_std))
            self.register_buffer("tgt_mean", torch.from_numpy(tgt_mean))
            self.register_buffer("tgt_std", torch.from_numpy(tgt_std))

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """x: (1, seq_len, n_features) — raw (un-normalised) values."""
            x_norm = (x - self.feat_mean) / self.feat_std
            y_norm = self.core(x_norm)
            return y_norm * self.tgt_std + self.tgt_mean

    wrapped = NormalisedGRU(model, feat_mean, feat_std, tgt_mean, tgt_std)
    scripted = torch.jit.script(wrapped)
    scripted.save(str(output_path))

    console.print(
        Panel(
            f"[green]Model saved to[/green] {output_path.resolve()}\n"
            f"[green]Best validation loss:[/green] {best_val_loss:.6f}\n\n"
            f"Add to [bold]simulator_init_state.toml[/bold]:\n"
            f'  [yellow]gru_model_path[/yellow] = "{output_path.resolve()}"',
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
    default=Path("models/gru_residual.pt"),
    show_default=True,
    help="Output path for the TorchScript model.",
)
@click.option(
    "--epochs",
    type=int,
    default=100,
    show_default=True,
    help="Number of training epochs.",
)
@click.option(
    "--seq-len", type=int, default=20, show_default=True, help="Input sequence length."
)
@click.option(
    "--hidden-size", type=int, default=64, show_default=True, help="GRU hidden size."
)
@click.option(
    "--num-layers", type=int, default=2, show_default=True, help="Number of GRU layers."
)
@click.option(
    "--batch-size", type=int, default=64, show_default=True, help="Training batch size."
)
@click.option(
    "--lr", type=float, default=1e-3, show_default=True, help="Adam learning rate."
)
def main(csv, output, epochs, seq_len, hidden_size, num_layers, batch_size, lr):
    """Train a GRU residual model for sim-to-real gap reduction."""
    train(csv, output, epochs, seq_len, hidden_size, num_layers, batch_size, lr)


if __name__ == "__main__":
    main()

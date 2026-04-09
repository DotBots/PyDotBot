import random

import click
from rich import print

# --- Configuration ---
WIDTH_NODES_DEFAULT = 5  # Robots per row
HEIGHT_NODES_DEFAULT = 5  # Number of rows
START_X_DEFAULT = 120  # Starting X position in mm
START_Y_DEFAULT = 120  # Starting Y position in mm
SEP_X_DEFAULT = 240  # Separation between columns
SEP_Y_DEFAULT = 240  # Separation between rows


def generate_lattice_toml(
    width_count,
    height_count,
    start_x,
    start_y,
    sep_x,
    sep_y,
    direction=None,
    control_loop_library_path=None,
):
    output_lines = []

    for row in range(height_count):
        for col in range(width_count):
            bot_id = row * width_count + col + 1
            address = f"AAAAAAAA{bot_id:08X}"

            # Calculate positions
            pos_x = start_x + (col * sep_x)
            pos_y = start_y + (row * sep_y)

            # Randomize direction between 0 and 360
            if direction is None:
                direction = random.randint(0, 360)

            # Manually build the TOML entry string to preserve underscores
            output_lines.append("[[dotbots]]")
            output_lines.append(f'address = "{address}"')
            output_lines.append("calibrated = 0xff")
            output_lines.append(f"pos_x = {pos_x:_}")
            output_lines.append(f"pos_y = {pos_y:_}")
            output_lines.append(f"direction = {direction}")
            if control_loop_library_path is not None:
                output_lines.append(
                    f'custom_control_loop_library = "{control_loop_library_path}"'
                )
            output_lines.append("")  # Empty line for readability

    return "\n".join(output_lines)


@click.command()
@click.argument(
    "output_path",
    type=click.Path(dir_okay=False, writable=True),
    default="init_state.toml",
)
@click.option(
    "--width",
    type=int,
    default=WIDTH_NODES_DEFAULT,
    help=f"Number of robots per row. Defaults to {WIDTH_NODES_DEFAULT}",
)
@click.option(
    "--height",
    type=int,
    default=HEIGHT_NODES_DEFAULT,
    help=f"Number of rows. Defaults to {HEIGHT_NODES_DEFAULT}",
)
@click.option(
    "--start-x",
    type=int,
    default=START_X_DEFAULT,
    help=f"Starting X position in mm. Defaults to {START_X_DEFAULT}",
)
@click.option(
    "--start-y",
    type=int,
    default=START_Y_DEFAULT,
    help=f"Starting Y position in mm. Defaults to {START_Y_DEFAULT}",
)
@click.option(
    "--sep-x",
    type=int,
    default=SEP_X_DEFAULT,
    help=f"Separation in mm between columns. Defaults to {SEP_X_DEFAULT}",
)
@click.option(
    "--sep-y",
    type=int,
    default=SEP_Y_DEFAULT,
    help=f"Separation in mm between rows. Defaults to {SEP_Y_DEFAULT}",
)
@click.option(
    "--direction",
    type=int,
    default=None,
    help="Default robot direction. Defaults to random generated direction",
)
@click.option(
    "--control-loop-library-path",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to an optional .so control loop library.",
)
def main(
    output_path,
    width,
    height,
    start_x,
    start_y,
    sep_x,
    sep_y,
    direction,
    control_loop_library_path,
):
    print(f"\nGenerating configuration with {width * height} robots.\n")
    print(f"  - Layout (row x col)      : {height} x {width}")
    print(f"  - Start coordinate (X,Y)  : {start_x}, {start_y}")
    print(f"  - Separation (X,Y)        : {sep_x}, {sep_y}\n")

    toml_string = generate_lattice_toml(
        width,
        height,
        start_x,
        start_y,
        sep_x,
        sep_y,
        direction,
        control_loop_library_path,
    )

    # Save to file
    with open(output_path, "w") as f:
        f.write(toml_string)

    print(f"Generated TOML file at {output_path}")


if __name__ == "__main__":
    main()

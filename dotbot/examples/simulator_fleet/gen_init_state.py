"""Write the simulator's initial state: N robots in a near-square block,
200 mm apart, centred on the field of site.toml, the top half of the rows
facing the staging strip and the bottom half the charging strip.

    python gen_init_state.py --n 500           # writes init-500.toml
"""

import argparse
import math
import pathlib

PITCH_MM = 200
FIELD_X, FIELD_Y, FIELD_W, FIELD_H = 2000, 10000, 16000, 16000
FACING_STAGING, FACING_CHARGING = 180, 0  # degrees, 0 facing +y (down)


def init_state(n: int) -> str:
    """The init file for `n` robots, rows filled left to right and the last
    one, when short, centred under the others."""
    columns = math.ceil(math.sqrt(n))
    rows = math.ceil(n / columns)
    if columns * PITCH_MM > FIELD_W or rows * PITCH_MM > FIELD_H:
        raise ValueError(f"{n} robots do not fit in the field at {PITCH_MM} mm")
    left = FIELD_X + (FIELD_W - (columns - 1) * PITCH_MM) // 2
    top = FIELD_Y + (FIELD_H - (rows - 1) * PITCH_MM) // 2
    lines = ["[network]", "pdr = 100", ""]
    for index in range(n):
        row, column = divmod(index, columns)
        in_row = min(columns, n - row * columns)
        shift = (columns - in_row) * PITCH_MM // 2
        direction = FACING_STAGING if row < rows // 2 else FACING_CHARGING
        lines += [
            "[[dotbots]]",
            f'address = "DE{index:014X}"',
            f"pos_x = {left + shift + column * PITCH_MM}",
            f"pos_y = {top + row * PITCH_MM}",
            f"direction = {direction}",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=500, help="how many robots")
    n = parser.parse_args().n
    pathlib.Path(__file__).with_name(f"init-{n}.toml").write_text(init_state(n))

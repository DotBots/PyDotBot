"""Write init.toml: 500 simulated robots in a 25 x 20 grid over the field of
site.toml, the top ten rows facing the staging strip and the bottom ten the
charging strip."""

import pathlib

COLUMNS, ROWS = 25, 20
FIELD_X, FIELD_Y, FIELD_W, FIELD_H = 2000, 10000, 16000, 16000
FACING_STAGING, FACING_CHARGING = 180, 0  # degrees, 0 facing +y (down)


def init_state() -> str:
    pitch_x, pitch_y = FIELD_W // COLUMNS, FIELD_H // ROWS
    lines = ["[network]", "pdr = 100", ""]
    for row in range(ROWS):
        for column in range(COLUMNS):
            index = row * COLUMNS + column
            direction = FACING_STAGING if row < ROWS // 2 else FACING_CHARGING
            lines += [
                "[[dotbots]]",
                f'address = "DE{index:014X}"',
                f"pos_x = {FIELD_X + pitch_x // 2 + column * pitch_x}",
                f"pos_y = {FIELD_Y + pitch_y // 2 + row * pitch_y}",
                f"direction = {direction}",
                "",
            ]
    return "\n".join(lines)


if __name__ == "__main__":
    pathlib.Path(__file__).with_name("init.toml").write_text(init_state())

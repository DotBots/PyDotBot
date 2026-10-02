# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A schema 4 calibration and the bytes it reaches a robot as.

swarmit's `tests/lh2_wire_fixture.py` carries the same file and the same
message bytes: the two packers must agree, so keep the copies identical.
"""

FIXTURE_ID = "9b12f56f622f0fb6"

FIXTURE_TOML = """\
schema_version = 4

[metadata]
created_at = "2026-09-10T09:12:00Z"
id = "9b12f56f622f0fb6"
robot = "dotbot-v3"
tag = "arena-relay"

[site]
name = "c405-arena"
anchor = "arena top-left corner, against the door wall of C405"

[validity]
valid_mm = [0, 0, 3330, 4000]

[[placement]]
index = 0
at = "arena:corners"
points_mm = [[47.0, 18.5], [1953.0, 18.5], [47.0, 1981.5], [1953.0, 1981.5]]
captured_at = "2026-09-10T09:10:41Z"
samples = [
  { station = 2, point = 0, count1 = [41290, 41291], count2 = [51728, 51727] },
  { station = 2, point = 1, count1 = [40877, 40878], count2 = [51102, 51101] },
  { station = 2, point = 2, count1 = [43166, 43167], count2 = [75717, 75716] },
  { station = 2, point = 3, count1 = [42810, 42811], count2 = [75104, 75103] },
]

[[station]]
index = 2
solved_from = "direct"
points = 4
residual_mm = 0.0
valid_mm = [0, 0, 2500, 4000]
homography = [[1523.4, -38.2, 1012.7], [41.9, 1531.8, 988.3], [0.2134, -0.0871, 1.0]]

[[station]]
index = 8
solved_from = "direct"
points = 4
residual_mm = 0.0
valid_mm = [800, 0, 3330, 4000]
homography = [[-1480.25, 12.5, 2950.0], [-20.75, 1502.125, 1010.5], [-0.1875, 0.0625, 1.0]]
"""

# One 84-byte swrmt_lh2_calibration_data_t per station: stations 2 and 8
# (channels 3 and 9), station mask 0x0104, each with its own rectangle, so a
# packer that keys by position or writes the union into every message fails.
MESSAGE_HEX = [
    (
        "0401000002000000cd6cbe44cdcc18c2cd2c7d449a9927429a79bf4433137744"
        "88855a3e7c61b2bd0000803f0000000000000000c4090000a00f000063343035"
        "2d6172656e610000000000009b12f56f622f0fb6"
    ),
    (
        "04010000080000000008b9c400004841006038450000a6c100c4bb4400a07c44"
        "000040be0000803d0000803f2003000000000000020d0000a00f000063343035"
        "2d6172656e610000000000009b12f56f622f0fb6"
    ),
]

# The same file without [site] and [validity], so each reader's defaults reach
# the wire: site "default" and valid_mm [0, 0, 10000, 10000].
DEFAULTS_FIXTURE_ID = "87453fc957d6f0ef"

DEFAULTS_FIXTURE_TOML = (
    FIXTURE_TOML.replace(
        '[site]\nname = "c405-arena"\n'
        'anchor = "arena top-left corner, against the door wall of C405"\n\n',
        "",
    )
    .replace("[validity]\nvalid_mm = [0, 0, 3330, 4000]\n\n", "")
    .replace("valid_mm = [0, 0, 2500, 4000]", "valid_mm = [0, 0, 10000, 10000]")
    .replace("valid_mm = [800, 0, 3330, 4000]", "valid_mm = [0, 0, 10000, 10000]")
    .replace(f'id = "{FIXTURE_ID}"', f'id = "{DEFAULTS_FIXTURE_ID}"')
)

DEFAULTS_MESSAGE_HEX = [
    (
        "0401000002000000cd6cbe44cdcc18c2cd2c7d449a9927429a79bf4433137744"
        "88855a3e7c61b2bd0000803f0000000000000000102700001027000064656661"
        "756c7400000000000000000087453fc957d6f0ef"
    ),
    (
        "04010000080000000008b9c400004841006038450000a6c100c4bb4400a07c44"
        "000040be0000803d0000803f0000000000000000102700001027000064656661"
        "756c7400000000000000000087453fc957d6f0ef"
    ),
]

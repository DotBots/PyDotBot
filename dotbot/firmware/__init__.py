"""DotBot firmware engine: fetch, flash, and read-back primitives.

The hardware-facing library behind the `dotbot fw` (artifacts) and
`dotbot device` (one cabled device) CLI namespaces. Originally vendored
from the standalone `dotbot-provision` package; the `provision` *command*
has since dissolved into `dotbot device flash-sandbox-host` /
`flash-gateway` / `flash-programmer` / `info`, so this package is named
for what it is — the firmware engine — not the retired command.
"""

# Troubleshooting

Fixes for the rough edges you're most likely to hit.

## Web UI won't load in Firefox

Firefox's HTTP/2 handling can break the WebSocket stream the web UI uses to talk
to the controller, so the map and joystick never come alive. Turn it off:

1. Press `Ctrl + L`, type `about:config`, and accept the warning.
2. Find `network.http.http2.websockets` and set it to `false`.
3. Reload the web UI.

Chromium-based browsers (Chrome, Edge, Brave) are unaffected.

## Web console is missing (console build not found)

Starting the controller or simulator logs:

```
Console build not found at .../dotbot/console-web/dist; /console will be unavailable.
```

The web console ships inside the published wheel but is **not** built by a
plain source checkout, so a git clone (or a wheel-less install) has no
`dotbot/console-web/dist/`. The controller and its REST/WebSocket API still run -
only the browser UI is unavailable. Fixes:

- **From PyPI** - install the wheel, which bundles the console: `pip install pydotbot`.
- **From a git checkout** - build it once: `cd dotbot/console-web && npm install && npm run build`.

## Calibration refused: `unsupported calibration schema_version 2`

The LH2 calibration file predates PyDotBot 0.32.0. Re-solve it from its stored
samples and reflash the robots by cable, as in
[Upgrading from schema 2](../guides/lh2-calibration.md#upgrading-from-schema-2).

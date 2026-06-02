# Troubleshooting

Fixes for the rough edges you're most likely to hit.

## Web UI won't load in Firefox

Firefox's HTTP/2 handling can break the WebSocket stream the web UI uses to talk
to the controller, so the map and joystick never come alive. Turn it off:

1. Press `Ctrl + L`, type `about:config`, and accept the warning.
2. Find `network.http.http2.websockets` and set it to `false`.
3. Reload the web UI.

Chromium-based browsers (Chrome, Edge, Brave) are unaffected.

## Web UI is missing (frontend build not found)

Starting the controller or simulator logs:

```
Frontend build not found at .../dotbot/frontend/build; the web UI will be unavailable.
```

The React web UI ships inside the published wheel but is **not** built by a
plain source checkout, so a git clone (or a wheel-less install) has no
`dotbot/frontend/build/`. The controller and its REST/WebSocket API still run -
only the browser UI is unavailable. Fixes:

- **From PyPI** - install the wheel, which bundles the UI: `pip install --pre pydotbot`.
- **From a git checkout** - build the UI once: `cd dotbot/frontend && npm install && npm run build`.

On a version without this check, the same cause surfaces as a startup crash,
`RuntimeError: Directory '.../dotbot/frontend/build' does not exist`.

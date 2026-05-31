# Troubleshooting

Fixes for the rough edges you're most likely to hit.

## Web UI won't load in Firefox

Firefox's HTTP/2 handling can break the WebSocket stream the web UI uses to talk
to the controller, so the map and joystick never come alive. Turn it off:

1. Press `Ctrl + L`, type `about:config`, and accept the warning.
2. Find `network.http.http2.websockets` and set it to `false`.
3. Reload the web UI.

Chromium-based browsers (Chrome, Edge, Brave) are unaffected.

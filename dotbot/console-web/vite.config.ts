import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxies: the console talks same-origin, vite forwards to the two backends.
//   /controller -> PyDotBot controller (REST + WS), default :8000
//   /swarmit    -> swarmit status server (real or fake), default :8001
// Override with CONTROLLER_TARGET / SWARMIT_TARGET env vars when the default
// ports are occupied by another controller/swarmit instance.
const controllerTarget =
  process.env.CONTROLLER_TARGET ?? "http://localhost:8000";
const swarmitTarget = process.env.SWARMIT_TARGET ?? "http://localhost:8001";

export default defineConfig({
  // Relative asset URLs: the production build is mounted at /console by the
  // controller; the dev server stays at /. API paths are absolute either way.
  base: "./",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/controller": {
        target: controllerTarget,
        ws: true,
      },
      "/swarmit": {
        target: swarmitTarget,
        rewrite: (path) => path.replace(/^\/swarmit/, ""),
      },
    },
  },
});

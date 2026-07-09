import { LH2Position, MapSize, PyDotBot, RgbLed, SwarmitNode } from "./types";

// Same-origin in dev thanks to the vite proxy (see vite.config.ts).
const CONTROLLER = "/controller";
const SWARMIT = "/swarmit";

export async function fetchDotBots(): Promise<PyDotBot[]> {
  const res = await fetch(`${CONTROLLER}/dotbots`);
  return res.json();
}

export async function fetchMapSize(): Promise<MapSize> {
  const res = await fetch(`${CONTROLLER}/map_size`);
  return res.json();
}

export async function fetchSwarmitStatus(): Promise<Record<string, SwarmitNode>> {
  const res = await fetch(`${SWARMIT}/status`);
  const body = await res.json();
  return body.response ?? {};
}

export async function putMoveRaw(
  address: string,
  application: number,
  left: number,
  right: number,
): Promise<void> {
  await fetch(`${CONTROLLER}/dotbots/${address}/${application}/move_raw`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ left_x: 0, left_y: left, right_x: 0, right_y: right }),
  });
}

export async function putRgbLed(
  address: string,
  application: number,
  led: RgbLed,
): Promise<void> {
  await fetch(`${CONTROLLER}/dotbots/${address}/${application}/rgb_led`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(led),
  });
}

export async function putWaypoints(
  address: string,
  application: number,
  threshold: number,
  waypoints: LH2Position[],
): Promise<void> {
  await fetch(`${CONTROLLER}/dotbots/${address}/${application}/waypoints`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold, waypoints }),
  });
}

export function controllerWsUrl(): string {
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}${CONTROLLER}/ws/status`;
}

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

// --- SwarmIT orchestration (write path; same contract as the real server) ---

export async function swarmitAction(
  action: "start" | "stop" | "reset",
  devices?: string[],
): Promise<void> {
  await fetch(`${SWARMIT}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(devices && devices.length ? { devices } : {}),
  });
}

export interface FlashEvent {
  type: "flash_started" | "chunk" | "device_done" | "complete" | "error";
  addr?: string;
  acked?: number;
  total?: number;
  devices?: string[];
  total_chunks?: number;
  success?: boolean;
  all_success?: boolean;
  message?: string;
}

// Split an SSE buffer into parsed `data:` payloads plus the trailing
// incomplete remainder (kept for the next chunk). Malformed frames are
// skipped.
export function parseSseChunk<T>(buf: string): { events: T[]; rest: string } {
  const events: T[] = [];
  let idx;
  while ((idx = buf.indexOf("\n\n")) >= 0) {
    const frame = buf.slice(0, idx);
    buf = buf.slice(idx + 2);
    const line = frame.split("\n").find((l) => l.startsWith("data: "));
    if (!line) continue;
    try {
      events.push(JSON.parse(line.slice(6)));
    } catch {
      /* skip malformed frame */
    }
  }
  return { events, rest: buf };
}

// POST /flash/stream and feed each SSE event to the callback.
export async function flashStream(
  firmwareB64: string,
  devices: string[] | undefined,
  onEvent: (ev: FlashEvent) => void,
): Promise<void> {
  const res = await fetch(`${SWARMIT}/flash/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      firmware_b64: firmwareB64,
      ...(devices && devices.length ? { devices } : {}),
    }),
  });
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const { events, rest } = parseSseChunk<FlashEvent>(buf);
    buf = rest;
    events.forEach(onEvent);
  }
}

export function swarmitEventsUrl(): string {
  return `${SWARMIT}/events`;
}

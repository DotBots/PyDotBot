// Client-side state of the MRTA mode toggle.
//
// MRTA mode does not run in the controller. It is a separate process
// (dotbot-logistics' `mrta_mode` package) that drives PIBT-planned navigation
// by watching the controller's own REST + WS surface, and the console reaches
// it through a /mrta/* proxy exactly the way it reaches swarmit through
// /swarmit/*. The console therefore never owns the mode's state: it renders
// what that process reports.
//
// Which is why "unavailable" is a first-class state rather than an error. No
// MRTA server behind the proxy is the NORMAL case - the console is fully
// useful without it - so the button has to look absent, not broken.
//
// And why the toggle is not a boolean. Turning MRTA on builds a whole session:
// it snapshots the fleet, so ON is a fresh PIBT world every time rather than a
// resume. Turning it off stops the bots and has to wait for the in-flight
// planning tick to finish first. Both take seconds, and a second click landing
// mid-transition would start a second session driving the same bots - hence
// the two busy states, which the button renders as disabled.

export type MrtaState = "off" | "connecting" | "on" | "stopping" | "unavailable";

export interface MrtaStatus {
  state: MrtaState;
  /** Fleet size the running session snapshotted; null when not running. */
  bots: number | null;
  /** Why it is off, or what it is doing - surfaced in the tooltip. */
  detail: string | null;
}

export const MRTA_UNAVAILABLE: MrtaStatus = { state: "unavailable", bots: null, detail: null };

// "unavailable" is the console's own word for "I could not reach the MRTA
// server". A server reporting it about itself would be a contradiction, so it
// is deliberately not accepted from the wire.
const REPORTABLE: readonly string[] = ["off", "connecting", "on", "stopping"];

export function parseStatus(body: unknown): MrtaStatus {
  if (typeof body !== "object" || body === null) return MRTA_UNAVAILABLE;
  const raw = body as Record<string, unknown>;
  if (typeof raw.state !== "string" || !REPORTABLE.includes(raw.state)) return MRTA_UNAVAILABLE;
  return {
    state: raw.state as MrtaState,
    bots: typeof raw.bots === "number" ? raw.bots : null,
    detail: typeof raw.detail === "string" && raw.detail ? raw.detail : null,
  };
}

export function isBusy(state: MrtaState): boolean {
  return state === "connecting" || state === "stopping";
}

export function canToggle(state: MrtaState): boolean {
  return state === "off" || state === "on";
}

/** The `on` value to POST, or null when the button must not act. */
export function toggleTarget(state: MrtaState): boolean | null {
  if (state === "off") return true;
  if (state === "on") return false;
  return null;
}

/** Where the button jumps the instant it is clicked, before the server answers. */
export function optimisticState(state: MrtaState): MrtaState {
  if (state === "off") return "connecting";
  if (state === "on") return "stopping";
  return state;
}

export type MrtaTone = "off" | "busy" | "on" | "gone";

export interface MrtaLook {
  label: string;
  tone: MrtaTone;
  /** Tooltip. Says what a map click will do, because that is what the mode changes. */
  hint: string;
}

const CLICK_MEANS_PIBT =
  "MRTA is ON: clicking the map no longer drives a bot straight there - PIBT routes it cell by cell, avoiding every other bot.";
const CLICK_MEANS_DIRECT =
  "MRTA is OFF: clicking the map sends the bot straight to the point, as usual.";

export function describe(status: MrtaStatus): MrtaLook {
  switch (status.state) {
    case "on":
      return {
        label: "ON",
        tone: "on",
        hint:
          `${CLICK_MEANS_PIBT}` +
          (status.bots !== null ? ` Driving the ${status.bots} bots it saw when it started.` : "") +
          " Turning it off stops the bots.",
      };
    case "connecting":
      return {
        label: "STARTING",
        tone: "busy",
        hint: status.detail ?? "Building a PIBT session from the fleet as it is right now.",
      };
    case "stopping":
      return {
        label: "STOPPING",
        tone: "busy",
        hint: status.detail ?? "Stopping the bots and finishing the planning tick in flight.",
      };
    case "unavailable":
      return {
        label: "N/A",
        tone: "gone",
        hint: "No MRTA server behind /mrta. Start it in dotbot-logistics to enable this mode.",
      };
    default:
      return { label: "OFF", tone: "off", hint: `${CLICK_MEANS_DIRECT} ${status.detail ?? ""}`.trim() };
  }
}

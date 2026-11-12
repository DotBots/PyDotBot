import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PushRow } from "../shared/pushRows";
import type { UnifiedBot } from "../types";
import { sendPlan, sendStoppingApps, shortIds, type SendDeps } from "./pushSend";
import { ServeSheet } from "./ServeSheet";
import type { EditorContext, LibraryRow } from "./types";

const A = "C61037A3F6462B07";
const B = "C61037A3F6469E36";
const C = "C61037A3F646D163";
const row = (id: string, state: string): PushRow => ({ id, tail: id.slice(-6), state, holds: "aaaaaaaa", current: false, appStops: state === "Running" });

/** Robots whose app stops after one status poll, and a log of what was asked. */
function fakeDeps(opts: { pushFails?: string; stuck?: string[] } = {}) {
  const calls: string[] = [];
  let t = 0;
  let polls = 0;
  const deps: SendDeps = {
    stop: async (d) => void calls.push(`stop ${d ? d.join(",") : "all"}`),
    start: async (d) => void calls.push(`start ${d ? d.join(",") : "all"}`),
    status: async () => {
      polls += 1;
      const st = (id: string) => (polls > 1 && !(opts.stuck ?? []).includes(id) ? "Bootloader" : "Running");
      return Object.fromEntries([A, B, C].map((id) => [id, { device: "DotBotV3", status: st(id) }]));
    },
    push: async (cal, d) => {
      calls.push(`push ${cal} ${d.join(",")}`);
      if (opts.pushFails) throw new Error(opts.pushFails);
      return { stale: [] };
    },
    sleep: async (ms) => void (t += ms),
    now: () => t,
  };
  return { deps, calls };
}

describe("a send that stops the apps first", () => {
  it("stops the running robots, waits for their bootloader, pushes, then starts them again", async () => {
    const { deps, calls } = fakeDeps();
    const steps: string[] = [];
    const rows = [row(A, "Running"), row(B, "Running"), row(C, "Bootloader")];
    const out = await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B])), deps, (s) => steps.push(s));
    expect(calls).toEqual([`stop ${A},${B}`, `push cal1 ${A},${B}`, `start ${A},${B}`]);
    expect(steps).toEqual(["Stopping 2 apps…", "Sending to 2 robots…", "2 of 2 hold bench. Restarting 2 apps…"]);
    expect(out).toMatchObject({ error: "", sent: [A, B], restarted: [A, B] });
  });

  it("stops and starts the whole swarm when every robot is ticked", async () => {
    const { deps, calls } = fakeDeps();
    const rows = [row(A, "Running"), row(B, "Running"), row(C, "Running")];
    await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B, C])), deps, () => {});
    expect(calls).toEqual(["stop all", `push cal1 ${A},${B},${C}`, "start all"]);
  });

  it("starts again only the apps that were running", async () => {
    const { deps, calls } = fakeDeps();
    const rows = [row(A, "Running"), row(B, "Bootloader")];
    await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B])), deps, () => {});
    expect(calls).toEqual(["stop all", `push cal1 ${A},${B}`, `start ${A}`]);
  });

  it("sends nothing when a robot stays in its app, and names it by its tail", async () => {
    const { deps, calls } = fakeDeps({ stuck: [B] });
    const rows = [row(A, "Running"), row(B, "Running"), row(C, "Bootloader")];
    const out = await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B])), deps, () => {});
    expect(calls).toEqual([`stop ${A},${B}`]);
    expect(out.sent).toEqual([]);
    expect(out.error).toContain("still in their app after a stop: …9E36");
    expect(out.error).not.toContain(B.slice(0, 8) + " ");
  });

  it("after a stop that timed out says how many apps stay stopped and names only them", async () => {
    const { deps } = fakeDeps({ stuck: [B] });
    const rows = [row(A, "Running"), row(B, "Running"), row(C, "Running")];
    const out = await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B, C])), deps, () => {});
    expect(out.stopped).toEqual([A, C]);
    expect(out.error).toContain("2 apps stay stopped");
    expect(out.error).toContain(`\`dotbot swarm -d ${A},${C} start\``);
  });

  it("suggests a swarm-wide start only when every robot sent was running", async () => {
    const { deps } = fakeDeps({ pushFails: "no robot answered" });
    const rows = [row(A, "Running"), row(B, "Bootloader")];
    const out = await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B])), deps, () => {});
    expect(out.error).toContain(`\`dotbot swarm -d ${A} start\``);
    const all = fakeDeps({ pushFails: "no robot answered" });
    const both = [row(A, "Running"), row(B, "Running")];
    const out2 = await sendStoppingApps("cal1", "bench", sendPlan(both, new Set([A, B])), all.deps, () => {});
    expect(out2.error).toContain("`dotbot swarm start`");
  });

  it("leaves the apps stopped and says so when the push is refused", async () => {
    const { deps, calls } = fakeDeps({ pushFails: `push refused: in their app: ${A}, ${B}. Stop them first with \`dotbot swarm -d ${A},${B} stop\`.` });
    const rows = [row(A, "Running"), row(B, "Running"), row(C, "Bootloader")];
    const out = await sendStoppingApps("cal1", "bench", sendPlan(rows, new Set([A, B])), deps, () => {});
    expect(calls).toEqual([`stop ${A},${B}`, `push cal1 ${A},${B}`]);
    expect(out.error).toContain("in their app: …2B07, …9E36.");
    expect(out.error).toContain("2 apps stay stopped");
  });
});

describe("shortIds", () => {
  it("cuts ids to their tail outside commands only", () => {
    expect(shortIds(`refused: ${A}. Run \`dotbot swarm -d ${A} stop\``)).toBe(`refused: …2B07. Run \`dotbot swarm -d ${A} stop\``);
  });
});

describe("the serve sheet's send", () => {
  const lib = { id: "4640cfde014c7232", id8: "4640cfde", tag: "bench", spin: "s", in_frame: true, reading: null } as unknown as LibraryRow;
  const ctx = { served: lib, started_with: null, next_start: null, persist_path: null } as unknown as EditorContext;
  const bot = (id: string) => ({ id, state: "Running", swarmit: { info: { info_version: 4, lh2_calibration_id: "aaaaaaaaaaaaaaaa" } } }) as unknown as UnifiedBot;

  it("on a refused push shows the error and offers no next step", async () => {
    const { deps } = fakeDeps({ pushFails: "push refused: no robot answered" });
    render(<ServeSheet row={lib} served={lib} context={ctx} bots={[bot(A), bot(B)]} site="s" onClose={() => {}} onServed={() => {}} onStale={async () => ctx} onVerify={() => {}} deps={deps} />);
    expect(screen.getByTestId("serve-send").textContent).toBe("Stop 2 apps and send to 2");
    await act(async () => void fireEvent.click(screen.getByTestId("serve-send")));
    expect(screen.getByTestId("serve-result").textContent).toContain("Not sent: push refused: no robot answered");
    expect(screen.queryByTestId("serve-verify")).toBeNull();
  });

  it("after a send names the next step by whether the site is anchored", async () => {
    const { deps } = fakeDeps();
    render(<ServeSheet row={lib} served={lib} context={ctx} bots={[bot(A), bot(B)]} site="s" onClose={() => {}} onServed={() => {}} onStale={async () => ctx} onVerify={() => {}} deps={deps} />);
    await act(async () => void fireEvent.click(screen.getByTestId("serve-send")));
    expect(screen.getByTestId("serve-result").textContent).toContain("2 of 2 hold bench. Restarted 2 apps.");
    expect(screen.getByTestId("serve-verify").textContent).toBe("Anchor the frame");
  });
});

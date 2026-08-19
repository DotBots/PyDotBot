import React, { useState } from "react";

import { UnifiedBot } from "./types";

// Right-side inspector: the low-level layer next to the map's high-level one.
// Renders what `dotbot swarm info` prints, from the same /status payload, and
// stacks one card per selected bot the way that command prints one panel per
// device. Everything is plain text in normal flow, so it selects and copies.
//
// swarmit serves the display strings it computes (reset_cause, fault_name,
// image_*_name, lh2_summary), so this renders them rather than keeping a
// second copy of the vocabulary in TypeScript.
export function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const pad = (n: number) => String(n).padStart(2, "0");
  if (h) return `${h}h ${pad(m)}m ${pad(s)}s`;
  if (m) return `${m}m ${pad(s)}s`;
  return `${s}s`;
}

// swarmit distinguishes a device that never answered from one reporting zero
// homographies: one is re-provisioned, the other is a fetch that has not
// landed. The server words both; absence here means the former.
export function formatLh2(bot: UnifiedBot): string {
  return bot.swarmit?.info?.lh2_summary ?? "unknown (no device info)";
}

const hex32 = (v: number) => `0x${(v >>> 0).toString(16).padStart(8, "0")}`;

// The plain-text form, so one click hands over exactly what a bug report wants.
export function infoText(bot: UnifiedBot): string {
  const sw = bot.swarmit;
  const info = sw?.info;
  const out: string[] = [bot.id];
  out.push(`Type              ${bot.deviceType}`);
  out.push(`Status            ${bot.state}`);
  out.push(`Battery           ${bot.battery.toFixed(2)}V`);
  out.push(
    `Position          ${bot.position ? `${Math.round(bot.position.x)}, ${Math.round(bot.position.y)}` : "no fix"}`,
  );
  if (info) {
    out.push("");
    out.push(`Image             ${info.image_name || "(unnamed)"}`);
    out.push(`  digest          ${info.image_digest}`);
    out.push(`  size            ${info.image_size ?? 0} B`);
    out.push(
      `  state           ${info.image_state_name ?? info.image_state} / ${info.image_result_name ?? info.image_result}`,
    );
    out.push("");
    out.push(`Sandbox fw        bootloader  ${info.bl_version}`);
    out.push(`                  netcore     ${info.net_version}`);
    out.push(`Uptime            ${formatUptime(info.uptime_s)}   (boot #${info.boot_count})`);
  }
  out.push("");
  out.push(`LH2 calibration   ${formatLh2(bot)}`);
  if (sw?.reset_reason !== undefined) {
    out.push("");
    out.push(`Last reset        ${bot.resetCause}`);
    out.push(`  reset_reason    ${hex32(sw.reset_reason)}`);
    out.push(`  fault           ${sw.fault_name ?? sw.fault}`);
    if (sw.fault) {
      out.push(`  cfsr            ${hex32(sw.cfsr ?? 0)}`);
      out.push(`  sfsr            ${hex32(sw.sfsr ?? 0)}`);
      out.push(`  pc              ${hex32(sw.pc ?? 0)}`);
      out.push(`  lr              ${hex32(sw.lr ?? 0)}`);
    }
  }
  return out.join("\n");
}

const label: React.CSSProperties = {
  fontSize: 9,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
};
const mono: React.CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 11 };

const Row: React.FC<{ k: string; v: string; indent?: boolean; accent?: boolean }> = ({
  k,
  v,
  indent,
  accent,
}) => (
  <div style={{ display: "flex", gap: 8, padding: "1px 0", paddingLeft: indent ? 10 : 0 }}>
    <div style={{ ...mono, color: "var(--muted)", flex: "none", width: 96 }}>{k}</div>
    <div style={{ ...mono, color: accent ? "var(--accent)" : "var(--text)", wordBreak: "break-all" }}>
      {v}
    </div>
  </div>
);

const Card: React.FC<{ bot: UnifiedBot }> = ({ bot }) => {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);
  const sw = bot.swarmit;
  const info = sw?.info;

  const copy = (text: string) => {
    navigator.clipboard?.writeText(text).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1200);
      },
      () => undefined,
    );
  };

  return (
    <div
      style={{
        border: "1px solid var(--hairline)",
        borderRadius: 10,
        padding: 12,
        marginBottom: 10,
        background: "var(--elevated)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <div style={{ ...mono, fontSize: 12, fontWeight: 600, flex: 1, wordBreak: "break-all" }}>
          {bot.id}
        </div>
        <div
          onClick={() => copy(infoText(bot))}
          title="Copy this panel as text"
          style={{
            ...mono,
            fontSize: 10,
            cursor: "pointer",
            padding: "2px 7px",
            borderRadius: 6,
            border: "1px solid var(--hairline)",
            color: copied ? "var(--accent)" : "var(--muted)",
            flex: "none",
          }}
        >
          {copied ? "copied" : "copy"}
        </div>
      </div>

      <Row k="Type" v={bot.deviceType} />
      <Row k="Status" v={bot.state} />
      <Row k="Battery" v={`${bot.battery.toFixed(2)}V`} />
      <Row
        k="Position"
        v={bot.position ? `${Math.round(bot.position.x)}, ${Math.round(bot.position.y)}` : "no fix"}
      />

      {info && (
        <>
          <div style={{ height: 8 }} />
          <Row k="Image" v={info.image_name || "(unnamed)"} />
          <Row k="digest" v={info.image_digest} indent />
          <Row k="size" v={`${info.image_size ?? 0} B`} indent />
          <Row
            k="state"
            v={`${info.image_state_name ?? info.image_state} / ${info.image_result_name ?? info.image_result}`}
            indent
          />
          <div style={{ height: 8 }} />
          <Row k="Sandbox fw" v={`bl   ${info.bl_version}`} />
          <Row k="" v={`net  ${info.net_version}`} />
          <Row k="Uptime" v={`${formatUptime(info.uptime_s)}  (boot #${info.boot_count})`} />
        </>
      )}

      <div style={{ height: 8 }} />
      <Row k="LH2 calib" v={formatLh2(bot)} />

      {sw?.reset_reason !== undefined && (
        <>
          <div style={{ height: 8 }} />
          <Row k="Last reset" v={bot.resetCause ?? "unknown"} accent={bot.crashed} />
          <Row k="reset_reason" v={hex32(sw.reset_reason)} indent />
          <Row k="fault" v={sw.fault_name ?? String(sw.fault)} indent />
          {Boolean(sw.fault) && (
            <>
              <Row k="cfsr" v={hex32(sw.cfsr ?? 0)} indent />
              <Row k="sfsr" v={hex32(sw.sfsr ?? 0)} indent />
              <Row k="pc" v={hex32(sw.pc ?? 0)} indent />
              <Row k="lr" v={hex32(sw.lr ?? 0)} indent />
            </>
          )}
        </>
      )}

      {(sw?.raw || info?.raw) && (
        <>
          <div style={{ height: 8 }} />
          <div
            onClick={() => setShowRaw((v) => !v)}
            style={{ ...mono, fontSize: 10, color: "var(--muted)", cursor: "pointer" }}
          >
            {showRaw ? "▾" : "▸"} wire bytes
          </div>
          {showRaw && (
            <div style={{ marginTop: 6 }}>
              {sw?.raw && <Row k="status" v={sw.raw} />}
              {info?.raw && <Row k="info" v={info.raw} />}
              <div
                onClick={() => copy(`status ${sw?.raw ?? ""}\ninfo ${info?.raw ?? ""}`)}
                style={{
                  ...mono,
                  fontSize: 10,
                  marginTop: 6,
                  cursor: "pointer",
                  color: "var(--muted)",
                  textDecoration: "underline",
                }}
              >
                copy wire bytes
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export const Inspector: React.FC<{
  bots: UnifiedBot[];
  onClose: () => void;
}> = ({ bots, onClose }) => (
  <div
    style={{
      width: 300,
      flex: "none",
      borderLeft: "1px solid var(--hairline)",
      background: "var(--surface)",
      display: "flex",
      flexDirection: "column",
      zIndex: 11,
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        padding: "12px 14px",
        borderBottom: "1px solid var(--hairline)",
      }}
    >
      <div style={{ ...label, flex: 1 }}>
        Inspector{bots.length > 1 ? ` · ${bots.length} bots` : ""}
      </div>
      <div onClick={onClose} title="Close inspector" style={{ cursor: "pointer", color: "var(--muted)" }}>
        &times;
      </div>
    </div>
    <div style={{ flex: 1, overflowY: "auto", padding: 12 }}>
      {bots.length === 0 ? (
        <div style={{ ...mono, color: "var(--muted)", fontSize: 11 }}>
          Select a bot to inspect it.
        </div>
      ) : (
        bots.map((b) => <Card key={b.id} bot={b} />)
      )}
    </div>
  </div>
);

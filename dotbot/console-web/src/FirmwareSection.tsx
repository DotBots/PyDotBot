import React, { useEffect, useRef, useState } from "react";

import { FirmwareFile, decodedSize, readFirmwareFile } from "./firmwareFile";
import {
  FirmwareEntry,
  load as loadHistory,
  togglePin as togglePinIn,
} from "./firmwareHistory";

// Firmware block at the top of the Testbed tab: one picker, one list, one
// flash button.
//
// There is deliberately no separate slot for the control-plane image. Pinning
// keeps it at the top of the list, which is the same affordance doing the same
// job - a dedicated slot showed the same file twice and put two competing red
// buttons in a 340px rail.

const label: React.CSSProperties = {
  fontSize: 9,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
};
const mono: React.CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 11 };

export function buildTime(ms: number, now = Date.now()): string {
  if (!ms) return "unknown";
  const mins = Math.round((now - ms) / 60000);
  if (mins < 1) return "just built";
  if (mins < 60) return `${mins}m old`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h old`;
  return `${Math.round(h / 24)}d old`;
}

const sizeKb = (b64: string) => `${(decodedSize(b64) / 1024).toFixed(1)} kB`;

const flashBtn = (enabled: boolean): React.CSSProperties => ({
  display: "block",
  width: "100%",
  textAlign: "center",
  padding: "8px 0",
  borderRadius: 8,
  fontSize: 12,
  fontWeight: 600,
  cursor: enabled ? "pointer" : "not-allowed",
  background: enabled ? "var(--accent)" : "var(--elevated)",
  color: enabled ? "#fff" : "var(--muted)",
  border: enabled ? "1px solid transparent" : "1px solid var(--hairline)",
});

const pickerBtn: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  background: "var(--elevated)",
  border: "1px dashed var(--hairline)",
  borderRadius: 8,
  padding: "9px 10px",
  cursor: "pointer",
  textAlign: "center",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
  ...mono,
};

interface Props {
  targetCount: number;
  flashing: boolean;
  onFlash: (image: FirmwareFile) => void;
}

export const FirmwareSection: React.FC<Props> = (props) => {
  const [open, setOpen] = useState(true);
  const [armed, setArmed] = useState<FirmwareFile | null>(null);
  const [history, setHistory] = useState<FirmwareEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [startAfter, setStartAfter] = useState(
    () => window.localStorage.getItem("dotbot.console.startAfterFlash") === "1",
  );
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setHistory(loadHistory());
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      "dotbot.console.startAfterFlash",
      startAfter ? "1" : "0",
    );
  }, [startAfter]);

  const pick = async (f: File | undefined) => {
    if (!f) return;
    setError(null);
    try {
      setArmed(await readFirmwareFile(f));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const flash = (image: FirmwareFile | null) => {
    if (!image || props.flashing) return;
    props.onFlash(image);
    // Re-read rather than guess: useOrchestration owns the write.
    setTimeout(() => setHistory(loadHistory()), 0);
  };

  const row = (
    name: string,
    b64: string,
    lastModified: number,
    extra?: React.ReactNode,
  ) => (
    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
      {extra}
      <div
        title={`${name} · ${sizeKb(b64)} · built ${new Date(lastModified).toLocaleString()}`}
        style={{ ...mono, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {name}
      </div>
      <div style={{ ...mono, fontSize: 9, color: "var(--muted)", flex: "none" }}>
        {buildTime(lastModified)}
      </div>
    </div>
  );

  return (
    <div style={{ borderBottom: "1px solid var(--hairline)", padding: "10px 12px" }}>
      <div
        onClick={() => setOpen((v) => !v)}
        style={{ ...label, cursor: "pointer", display: "flex", alignItems: "center", gap: 6 }}
      >
        <span>{open ? "▾" : "▸"}</span> Firmware
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          <input
            ref={fileRef}
            type="file"
            accept=".bin,application/octet-stream"
            style={{ display: "none" }}
            // Clearing the value first makes re-picking the same path fire a
            // change event, so a rebuilt image is re-read instead of flashing
            // the bytes captured the first time it was chosen.
            onClick={(e) => {
              (e.currentTarget as HTMLInputElement).value = "";
            }}
            onChange={(e) => pick(e.target.files?.[0])}
          />
          <div
            onClick={() => fileRef.current?.click()}
            style={{ ...pickerBtn, textAlign: armed ? "left" : "center", borderStyle: armed ? "solid" : "dashed" }}
          >
            {armed ? row(armed.name, armed.b64, armed.lastModified) : "Choose a .bin file…"}
          </div>

          {history.length > 0 && (
            <>
              <div style={{ ...label, margin: "8px 0 4px" }}>Recent</div>
              <div
                style={{
                  maxHeight: 108,
                  overflowY: "auto",
                  border: "1px solid var(--hairline)",
                  borderRadius: 8,
                }}
              >
                {history.map((h) => {
                  const picked = armed?.b64 === h.b64;
                  return (
                    <div
                      key={`${h.name}-${h.ts}`}
                      onClick={() => setArmed({ name: h.name, b64: h.b64, lastModified: h.lastModified })}
                      title="Flash these exact bytes again"
                      style={{
                        padding: "6px 8px",
                        borderBottom: "1px solid var(--hairline)",
                        cursor: "pointer",
                        background: picked ? "var(--elevated)" : "transparent",
                        color: picked ? "var(--accent)" : "var(--text)",
                      }}
                    >
                      {row(
                        h.name,
                        h.b64,
                        h.lastModified,
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            setHistory(togglePinIn(h));
                          }}
                          title={h.pinned ? "Unpin" : "Pin to the top and keep"}
                          style={{ cursor: "pointer", fontSize: 10, color: h.pinned ? "var(--accent)" : "var(--muted)" }}
                        >
                          {h.pinned ? "★" : "☆"}
                        </span>,
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          <div
            onClick={() => flash(armed)}
            style={{ ...flashBtn(Boolean(armed) && !props.flashing && props.targetCount > 0), marginTop: 6 }}
          >
            &#9889;&nbsp;Flash {props.targetCount} device(s)
          </div>

          {error && (
            <div style={{ fontSize: 11, color: "var(--accent)", marginTop: 6 }}>{error}</div>
          )}

          <label style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 8, cursor: "pointer", fontSize: 11, color: "var(--muted)" }}>
            <input
              type="checkbox"
              checked={startAfter}
              onChange={(e) => setStartAfter(e.target.checked)}
            />
            Start after flashing
          </label>
        </div>
      )}
    </div>
  );
};

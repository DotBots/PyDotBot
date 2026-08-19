import React, { useEffect, useRef, useState } from "react";

import { FirmwareEntry, decodedSize, load as loadHistory } from "./firmwareHistory";

// v1 flash dialog, reading a real image off disk. swarmit takes the image as
// base64 in the request body, so the file never touches the controller's
// filesystem and any .bin the operator can see is flashable.

// Base64 without blowing the argument limit on a multi-hundred-kB image, which
// String.fromCharCode(...bytes) would do.
export function toBase64(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

export function relativeTime(ts: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ts) / 1000));
  if (s < 60) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

const labelStyle: React.CSSProperties = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
};

interface FlashDialogProps {
  open: boolean;
  targetCount: number;
  targetLabel: string;
  onClose: () => void;
  onFlash: (firmwareB64: string, firmwareName: string) => void;
}

export const FlashDialog: React.FC<FlashDialogProps> = (props) => {
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<{ name: string; size: number; b64: string } | null>(null);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<FirmwareEntry[]>([]);

  // Re-read on open: another tab may have flashed since this one last looked.
  useEffect(() => {
    if (props.open) setHistory(loadHistory());
  }, [props.open]);

  const pick = async (f: File | undefined) => {
    if (!f) return;
    setReading(true);
    setError(null);
    try {
      const buf = new Uint8Array(await f.arrayBuffer());
      if (buf.length === 0) throw new Error("file is empty");
      setFile({ name: f.name, size: buf.length, b64: toBase64(buf) });
    } catch (e) {
      setFile(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReading(false);
    }
  };

  if (!props.open) return null;
  return (
    <div
      onClick={props.onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.55)",
        zIndex: 40,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 400,
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 14,
          padding: 22,
          boxShadow: "0 20px 60px rgba(0,0,0,.5)",
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Flash firmware</div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 18 }}>
          Over-the-air flash to <span style={{ color: "var(--text)" }}>{props.targetCount}</span> device(s) &middot;{" "}
          {props.targetLabel}
        </div>
        <div style={{ fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
          Firmware image
        </div>
        <input
          ref={fileRef}
          type="file"
          accept=".bin,application/octet-stream"
          style={{ display: "none" }}
          onChange={(e) => pick(e.target.files?.[0])}
        />
        <div
          onClick={() => fileRef.current?.click()}
          style={{
            width: "100%",
            boxSizing: "border-box",
            background: "var(--elevated)",
            border: `1px dashed ${file ? "var(--accent)" : "var(--hairline)"}`,
            borderRadius: 8,
            padding: "14px 12px",
            color: file ? "var(--text)" : "var(--muted)",
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            outline: "none",
            cursor: "pointer",
            marginBottom: error ? 8 : 22,
            textAlign: "center",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {reading
            ? "Reading..."
            : file
              ? `${file.name} · ${(file.size / 1024).toFixed(1)} kB`
              : "Choose a .bin image..."}
        </div>
        {error && (
          <div style={{ fontSize: 12, color: "var(--accent)", marginBottom: 14 }}>{error}</div>
        )}
        {history.length > 0 && (
          <>
            <div style={{ ...labelStyle, marginBottom: 6 }}>Recently flashed &middot; click to reuse</div>
            <div
              style={{
                maxHeight: 132,
                overflowY: "auto",
                border: "1px solid var(--hairline)",
                borderRadius: 8,
                marginBottom: 22,
              }}
            >
              {history.map((h) => {
                const picked = file?.b64 === h.b64;
                return (
                  <div
                    key={`${h.name}-${h.ts}`}
                    onClick={() => {
                      setError(null);
                      setFile({ name: h.name, size: decodedSize(h.b64), b64: h.b64 });
                    }}
                    title={`Flash this again · ${new Date(h.ts).toLocaleString()}`}
                    style={{
                      display: "flex",
                      gap: 10,
                      alignItems: "baseline",
                      padding: "7px 10px",
                      borderBottom: "1px solid var(--hairline)",
                      cursor: "pointer",
                      background: picked ? "var(--elevated)" : "transparent",
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 12,
                        color: picked ? "var(--accent)" : "var(--text)",
                        flex: 1,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {picked ? "\u25cf " : ""}
                      {h.name}
                    </div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", flex: "none" }}>
                      {(decodedSize(h.b64) / 1024).toFixed(1)} kB
                    </div>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", flex: "none" }}>
                      {relativeTime(h.ts)}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <div
            onClick={props.onClose}
            style={{
              padding: "9px 16px",
              borderRadius: 8,
              cursor: "pointer",
              fontSize: 13,
              background: "var(--elevated)",
              border: "1px solid var(--hairline)",
            }}
          >
            Cancel
          </div>
          <div
            onClick={() => {
              if (!file) return;
              props.onFlash(file.b64, file.name);
              props.onClose();
            }}
            title={file ? undefined : "Choose a firmware image first"}
            style={{
              padding: "9px 18px",
              borderRadius: 8,
              cursor: file ? "pointer" : "not-allowed",
              fontSize: 13,
              fontWeight: 600,
              background: file ? "var(--accent)" : "var(--elevated)",
              color: file ? "#fff" : "var(--muted)",
              border: file ? "1px solid transparent" : "1px solid var(--hairline)",
            }}
          >
            Flash {props.targetCount} device(s)
          </div>
        </div>
      </div>
    </div>
  );
};

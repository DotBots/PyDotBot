import qrcode from "qrcode-generator";
import React, { useEffect, useRef } from "react";

import { isLoopbackHost } from "./qr";

// The overlay behind the QR button: the phone URL as a scannable code, the
// same URL as text under it, and a warning when the URL only resolves here.

/** Canvas px per QR module. 6 keeps a long URL under 300 px on the card. */
const CELL = 6;
/** Quiet zone in modules. Four is the spec's minimum for a reliable scan. */
const MARGIN = 4;

const QrCanvas: React.FC<{ url: string }> = ({ url }) => {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    // Type 0 picks the smallest version that fits; M survives a phone camera
    // at an angle without growing the code much.
    const qr = qrcode(0, "M");
    qr.addData(url);
    qr.make();
    const modules = qr.getModuleCount();
    const px = (modules + MARGIN * 2) * CELL;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(px * dpr);
    canvas.height = Math.round(px * dpr);
    canvas.style.width = `${px}px`;
    canvas.style.height = `${px}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // A camera reads this, not a person, so the quiet zone and the modules
    // stay white and black in either theme.
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, px, px);
    ctx.fillStyle = "#000";
    for (let row = 0; row < modules; row++) {
      for (let col = 0; col < modules; col++) {
        if (qr.isDark(row, col)) {
          ctx.fillRect((col + MARGIN) * CELL, (row + MARGIN) * CELL, CELL, CELL);
        }
      }
    }
  }, [url]);

  return <canvas ref={ref} style={{ display: "block", borderRadius: 7 }} />;
};

export const QrCard: React.FC<{ url: string; onClose: () => void }> = ({ url, onClose }) => {
  const loopback = isLoopbackHost(new URL(url).hostname);
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        display: "grid",
        placeItems: "center",
        background: "rgba(0, 0, 0, 0.55)",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 12,
          padding: 20,
          maxWidth: 340,
          lineHeight: 1.55,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div style={{ fontWeight: 600, alignSelf: "flex-start" }}>Open this on a phone</div>
        <QrCanvas url={url} />
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            wordBreak: "break-all",
            background: "var(--elevated)",
            borderRadius: 7,
            padding: 9,
            width: "100%",
            boxSizing: "border-box",
          }}
        >
          {url}
        </div>
        {loopback && (
          <div style={{ fontSize: 12, color: "var(--accent)" }}>
            This URL only resolves on this machine, so a phone cannot open it. Start vite with{" "}
            <code style={{ fontFamily: "var(--font-mono)" }}>--host</code> and reload the page on
            the address it prints.
          </div>
        )}
      </div>
    </div>
  );
};

import React, { useEffect } from "react";

import { FixThumb } from "./FixThumb";
import { Icon } from "./icons";
import { residuals, when } from "./library";
import { moved } from "./coverage";
import type { LibraryRow, Rect } from "./types";

// Two calibrations side by side: their boxes, residuals and readings, and
// for two different spins the frame-invariant shape of the stations, which
// is what a moved tripod would change.

export const CompareSheet: React.FC<{ a: LibraryRow; b: LibraryRow; extent: [number, number]; onClose: () => void; onPreview: (row: LibraryRow) => void }> = ({
  a,
  b,
  extent,
  onClose,
  onPreview,
}) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  const sameSpin = a.spin === b.spin;
  const stations = [...new Set([...a.stations, ...b.stations].map((s) => s.index))].sort();
  const verdict = moved(a, [b]);
  const thumb = (r: LibraryRow) => (
    <FixThumb boxes={Object.fromEntries(r.stations.map((s) => [s.index, s.box])) as Record<number, Rect>} extent={r.in_frame ? extent : [r.fence[2], r.fence[3]]} size={90} />
  );
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="sheet wide" role="dialog" aria-modal="true" aria-label="Compare two calibrations" data-testid="compare-sheet">
        <button type="button" className="btn icon ghost x" aria-label="Close" onClick={onClose}>
          <Icon name="x" size={14} />
        </button>
        <h2>
          <Icon name="compare" size={16} /> Compare {a.id8} and {b.id8}
        </h2>
        <div className="sub">
          {sameSpin
            ? "One measurement: the same homographies, so the stations are where they were. Only where each station is trusted differs."
            : "Two spins: their frames differ, so positions are not compared; the stations' heights and distance apart do not depend on the frame, and a moved tripod would change them."}
        </div>
        <table className="ft">
          <thead>
            <tr>
              <th />
              {[a, b].map((r) => (
                <th key={r.id}>
                  <span className="mono" style={{ color: "var(--text)" }}>
                    {r.id8}
                  </span>{" "}
                  {r.tag || "no tag"}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Who gives the fix</td>
              <td>{thumb(a)}</td>
              <td>{thumb(b)}</td>
            </tr>
            <tr>
              <td>Reading</td>
              <td>{a.in_frame ? a.reading : "own frame"}</td>
              <td>{b.in_frame ? b.reading : "own frame"}</td>
            </tr>
            <tr>
              <td>Measured</td>
              <td className="m">{when(a.created_at)}</td>
              <td className="m">{when(b.created_at)}</td>
            </tr>
            <tr>
              <td>Residuals</td>
              <td className="m">{residuals(a)}</td>
              <td className="m">{residuals(b)}</td>
            </tr>
            {stations.map((s) => {
              const ga = a.geometry?.stations[String(s)];
              const gb = b.geometry?.stations[String(s)];
              return (
                <tr key={s}>
                  <td>S{s} height, estimated</td>
                  <td className="m">{ga ? `${ga.height_mm} mm` : "-"}</td>
                  <td className="m">
                    {gb ? `${gb.height_mm} mm` : "-"}
                    {ga && gb && <span className="muted"> ({gb.height_mm - ga.height_mm >= 0 ? "+" : ""}{gb.height_mm - ga.height_mm})</span>}
                  </td>
                </tr>
              );
            })}
            {Object.keys(a.geometry?.apart_mm ?? {}).map((pair) => (
              <tr key={pair}>
                <td>{pair.split("-").map((x) => `S${x}`).join("-")} apart, estimated</td>
                <td className="m">{a.geometry?.apart_mm[pair]} mm</td>
                <td className="m">{b.geometry?.apart_mm[pair] ?? "-"} mm</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className={`callout ${verdict.verdict === "moved?" ? "warn" : "ok"}`} style={{ marginTop: 12 }}>
          <div className="h">Moved? {verdict.verdict === "moved?" ? "maybe: a station's shape differs by more than 250 mm" : sameSpin ? "no: the same spin" : "no sign"}</div>
          A moved tripod would show here; a nudge of a few centimetres would not. These are estimates from the homographies, not tape measurements.
        </div>
        <footer>
          <span className="sp" style={{ flex: 1 }} />
          <button type="button" className="btn" onClick={() => onPreview(a)}>
            Preview {a.id8}
          </button>
          <button type="button" className="btn" onClick={() => onPreview(b)}>
            Preview {b.id8}
          </button>
          <button type="button" className="btn primary" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </>
  );
};

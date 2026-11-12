import React from "react";

import { CalibrationChip } from "./shared/CalibrationChip";
import { PAGE_NAME } from "./shared/pageName";
import { servedChip, SITE_EDITOR_PATH } from "./shared/served";
import type { Site } from "./types";

/** The top of Layers: the site the positions belong to, the calibration the
 * controller serves, and the way to edit the site in a tab of its own. */
export const SiteCard: React.FC<{ site: Site | null }> = ({ site }) => (
  <div
    data-testid="site-card"
    style={{
      border: "1px solid var(--hairline)",
      borderRadius: 8,
      padding: "9px 10px",
      marginBottom: 12,
      background: "var(--canvas)",
      display: "grid",
      gap: 7,
    }}
  >
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)" }}>
        Site
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600 }}>{site?.name ?? "unknown"}</span>
      <span style={{ flex: 1 }} />
      <a
        data-testid="edit-site"
        href={SITE_EDITOR_PATH}
        target="dotbot-site-editor"
        rel="noopener"
        title={`Open ${PAGE_NAME} in a new tab; the console and its Stop stay here`}
        style={{ fontSize: 12, fontWeight: 600 }}
      >
        Open {PAGE_NAME} ↗
      </a>
    </div>
    <CalibrationChip chip={servedChip(site?.calibration)} />
  </div>
);

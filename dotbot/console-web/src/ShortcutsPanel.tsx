import React, { useEffect, useRef } from "react";

import {
  CLOSE_KEY,
  SHORTCUTS_KEY,
  SHORTCUT_GROUPS,
  ShortcutGroup,
  isKey,
  isModifier,
  modifierLabel,
  onMac,
} from "./shortcuts";

import "./mapChrome.css";

// The shortcuts panel: every group of `SHORTCUT_GROUPS`, one table each, in
// a dialog over the view. Opening moves focus into it; closing gives focus
// back to whatever had it. Nothing holds focus in: Tab leaves as it would
// from any other panel, and the key that opened it closes it.

const Keys: React.FC<{ keys: string[]; mac: boolean }> = ({ keys, mac }) => (
  <span className="db-keys">
    {keys.map((key, i) => (
      <React.Fragment key={`${key}-${i}`}>
        {i > 0 && <span className="db-gesture">+</span>}
        {isModifier(key) ? (
          <kbd className="db-kbd">{modifierLabel(key, mac)}</kbd>
        ) : isKey(key) ? (
          <kbd className="db-kbd">{key}</kbd>
        ) : (
          <span className="db-gesture">{key}</span>
        )}
      </React.Fragment>
    ))}
  </span>
);

const Group: React.FC<{ group: ShortcutGroup; mac: boolean }> = ({
  group,
  mac,
}) => (
  <section aria-label={`${group.surface} shortcuts`}>
    <h3>{group.surface}</h3>
    <table>
      <tbody>
        {group.rows.map((row) => (
          <tr key={row.does}>
            <td>
              <Keys keys={row.keys} mac={mac} />
            </td>
            <td>{row.does}</td>
          </tr>
        ))}
      </tbody>
    </table>
  </section>
);

export const ShortcutsPanel: React.FC<{
  open: boolean;
  onClose: () => void;
  groups?: ShortcutGroup[];
}> = ({ open, onClose, groups = SHORTCUT_GROUPS }) => {
  const panelRef = useRef<HTMLDivElement>(null);
  const before = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    before.current = document.activeElement;
    panelRef.current?.focus();
    return () => {
      const el = before.current;
      if (el instanceof HTMLElement && el.isConnected) el.focus();
      before.current = null;
    };
  }, [open]);

  if (!open) return null;
  const mac = onMac();
  return (
    <div
      className="db-shortcuts-backdrop"
      data-testid="shortcuts-backdrop"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className="db-shortcuts"
        role="dialog"
        aria-modal="true"
        aria-labelledby="db-shortcuts-title"
        tabIndex={-1}
        onPointerDown={(e) => e.stopPropagation()}
      >
        <h2 id="db-shortcuts-title">Keyboard and mouse shortcuts</h2>
        {groups.map((group) => (
          <Group key={group.surface} group={group} mac={mac} />
        ))}
        <footer>
          <span>
            <kbd className="db-kbd">{CLOSE_KEY === "Escape" ? "Esc" : CLOSE_KEY}</kbd>{" "}
            or <kbd className="db-kbd">{SHORTCUTS_KEY}</kbd> closes
          </span>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </footer>
      </div>
    </div>
  );
};

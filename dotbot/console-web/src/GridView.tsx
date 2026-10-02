import React from "react";

import {
  appLabel,
  areaLabel,
  bootloaderLabel,
  calibrationDiffers,
  calibrationLabel,
  detailText,
  FleetContext,
  firmwareTooOld,
  headingLabel,
  positionLabel,
  reportsDetail,
  reportsLabel,
} from "./botFacts";
import { rowOpacity } from "./link";
import { store } from "./persisted";
import { UnifiedBot } from "./types";
import {
  Badge,
  BatteryCell,
  FilterBar,
  HeadingGlyph,
  LedDot,
  Pagination,
  ResetBadge,
  stateColor,
  stateLabel,
  TooOld,
  useQueriedBots,
  useViewQuery,
} from "./viewChrome";

/** How much a card says: the facts to act on, or nearly all the robot reports. */
export type CardSize = "compact" | "full";

const CARD_SIZE_KEY = "dotbot.console.gridCards";

function loadCardSize(): CardSize {
  try {
    return window.localStorage.getItem(CARD_SIZE_KEY) === '"full"' ? "full" : "compact";
  } catch {
    return "compact";
  }
}

const mono: React.CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" };
const oneLine: React.CSSProperties = { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" };

const CardSizeToggle: React.FC<{ size: CardSize; setSize: (s: CardSize) => void }> = ({ size, setSize }) => (
  <div
    role="group"
    aria-label="Card size"
    style={{ display: "flex", background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, padding: 2 }}
  >
    {(["compact", "full"] as const).map((s) => (
      <button
        key={s}
        aria-pressed={size === s}
        onClick={() => setSize(s)}
        style={{
          background: size === s ? "var(--elevated)" : "transparent",
          border: "none",
          borderRadius: 6,
          padding: "6px 10px",
          color: size === s ? "var(--text)" : "var(--muted)",
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        {s === "compact" ? "Compact" : "Full"}
      </button>
    ))}
  </div>
);

/** Position, heading and area on one line, the heading drawn rather than written. */
const WhereLine: React.FC<{ bot: UnifiedBot; ctx: FleetContext; degrees: boolean }> = ({ bot, ctx, degrees }) => {
  const area = areaLabel(bot, ctx.site);
  const heading = headingLabel(bot);
  return (
    <div style={{ ...mono, display: "flex", alignItems: "center", gap: 7, color: "var(--text)" }}>
      <HeadingGlyph bot={bot} />
      <span style={{ ...oneLine, color: "var(--muted)" }}>
        {positionLabel(bot) || "no position"}
        {degrees && heading && ` · ${heading}`}
        {area && ` · ${area}`}
      </span>
    </div>
  );
};

/** A compact card's chips: the bootloader version, then the exceptions - late
 * or silent reports and the two firmware warnings. */
const Chips: React.FC<{ bot: UnifiedBot; ctx: FleetContext }> = ({ bot, ctx }) => {
  const slipping = bot.link === "stale" || bot.link === "lost";
  const differs = calibrationDiffers(bot, ctx.calibrationId);
  const old = firmwareTooOld(bot);
  const bootloader = bootloaderLabel(bot);
  if (!bootloader && !slipping && !differs && !old) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {bootloader && <Badge title="Bootloader version, and the net core's when it differs">bl {bootloader}</Badge>}
      {slipping && <Badge title={reportsDetail(bot, ctx.now)}>{reportsLabel(bot, ctx.now)}</Badge>}
      {old && <TooOld />}
      {differs && (
        <Badge tone="warn" title={`The controller serves ${ctx.calibrationId.slice(0, 8)}`}>
          cal differs
        </Badge>
      )}
    </div>
  );
};

const Fact: React.FC<{ k: string; children: React.ReactNode; title?: string; extra?: React.ReactNode }> = ({
  k,
  children,
  title,
  extra,
}) => (
  <>
    <span style={{ fontSize: 10, color: "var(--muted)", whiteSpace: "nowrap" }}>{k}</span>
    <span title={title} style={{ ...mono, color: "var(--text)", minWidth: 0, overflowWrap: "anywhere" }}>
      {children}
      {extra && <span style={{ marginLeft: 6 }}>{extra}</span>}
    </span>
  </>
);

const dash = <span style={{ color: "var(--muted)" }}>—</span>;

interface GridViewProps {
  bots: UnifiedBot[];
  selection: Set<string>;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
  ctx: FleetContext;
}

export const GridView: React.FC<GridViewProps> = ({ bots, selection, onSelect, ctx }) => {
  const { q, setQ } = useViewQuery();
  const { rows, total, pages } = useQueriedBots(bots, q, ctx);
  const [size, setSizeState] = React.useState<CardSize>(loadCardSize);
  const setSize = (next: CardSize) => {
    setSizeState(next);
    store(CARD_SIZE_KEY, next);
  };
  const full = size === "full";
  // File-manager selection: click = single, shift+click = range from the
  // anchor in the current card order, cmd/ctrl = toggle.
  const anchorRef = React.useRef<string | null>(null);
  const cardClick = (e: React.MouseEvent, id: string) => {
    if (e.shiftKey && anchorRef.current) {
      const ids = rows.map((r) => r.id);
      const a = ids.indexOf(anchorRef.current);
      const b = ids.indexOf(id);
      if (a >= 0 && b >= 0) {
        onSelect(ids.slice(Math.min(a, b), Math.max(a, b) + 1), "add");
        return;
      }
    }
    if (e.metaKey || e.ctrlKey) {
      onSelect([id], "toggle");
      anchorRef.current = id;
      return;
    }
    // Plain click on the sole selected item deselects it.
    if (selection.has(id) && selection.size === 1) {
      onSelect([], "replace");
      anchorRef.current = null;
      return;
    }
    onSelect([id], "replace");
    anchorRef.current = id;
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "14px 16px",
        paddingTop: 58, // clear the floating view switcher
        background: "var(--canvas)",
      }}
      onClick={() => onSelect([], "replace")}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <div style={{ flex: 1 }}>
          <FilterBar q={q} setQ={setQ} total={total} />
        </div>
        <CardSizeToggle size={size} setSize={setSize} />
      </div>
      <div style={{ flex: 1, overflow: "auto" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(auto-fill, minmax(${full ? 260 : 212}px, 1fr))`,
            gap: 14,
            paddingBottom: 6,
          }}
        >
          {rows.map((b) => {
            const checked = selection.has(b.id);
            return (
              <div
                key={b.id}
                title={detailText(b, ctx)}
                data-link={b.link}
                onClick={(e) => {
                  e.stopPropagation();
                  cardClick(e, b.id);
                }}
                style={{
                  opacity: rowOpacity(b),
                  display: "flex",
                  flexDirection: "column",
                  gap: 9,
                  padding: "13px 14px",
                  borderRadius: 10,
                  background: "var(--surface)",
                  border: checked ? "1px solid var(--accent)" : "1px solid var(--hairline)",
                  boxShadow: checked ? "0 0 0 1px var(--accent)" : "none",
                  cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <LedDot bot={b} />
                  <ResetBadge bot={b} />
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 14 }}>{b.id.slice(-4)}</span>
                  <div style={{ flex: 1 }} />
                  <span
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      background: stateColor(b.state),
                      display: "inline-block",
                    }}
                  />
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>{stateLabel(b.state)}</span>
                </div>
                {full && (
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 10, color: "var(--muted)" }}>
                    <span style={{ fontFamily: "var(--font-mono)" }}>{b.id}</span>
                    <span title={reportsDetail(b, ctx.now)}>{reportsLabel(b, ctx.now)}</span>
                  </div>
                )}
                <BatteryCell bot={b} fill />
                <WhereLine bot={b} ctx={ctx} degrees={full} />
                {!full && appLabel(b) && (
                  <div style={{ ...mono, ...oneLine }} title={`App ${appLabel(b)}`}>
                    {b.swarmit?.info?.image_name || "(unnamed)"}
                  </div>
                )}
                {full && (
                  <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", columnGap: 10, rowGap: 4 }}>
                    <Fact k="App" title={appLabel(b)}>
                      {appLabel(b) || dash}
                    </Fact>
                    <Fact k="Bootloader" extra={firmwareTooOld(b) && <TooOld />}>
                      {bootloaderLabel(b) || dash}
                    </Fact>
                    <Fact
                      k="LH2 cal"
                      extra={
                        calibrationDiffers(b, ctx.calibrationId) && (
                          <Badge tone="warn" title={`The controller serves ${ctx.calibrationId.slice(0, 8)}`}>
                            differs
                          </Badge>
                        )
                      }
                    >
                      {calibrationLabel(b) || dash}
                    </Fact>
                    <Fact k="Device">{b.deviceType}</Fact>
                    {b.severity !== "normal" && <Fact k="Last reset">{b.resetCause ?? b.severity}</Fact>}
                  </div>
                )}
                {!full && <Chips bot={b} ctx={ctx} />}
              </div>
            );
          })}
        </div>
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <Pagination q={q} setQ={setQ} pages={pages} />
      </div>
    </div>
  );
};

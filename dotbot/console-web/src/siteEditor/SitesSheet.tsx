import React, { useEffect, useState } from "react";

import { createSite, fetchSites, switchSite, type NewSiteStart, type SiteList } from "./api";
import { Icon } from "./icons";
import { parseFloorSize, siteNameProblem, SITE_NAME_MAX } from "./sites";

// New site and Switch site. Both change which site the controller works in,
// so the page reloads on the new one once the controller has taken it.

const STARTS: { value: NewSiteStart; title: string; detail: string }[] = [
  { value: "empty", title: "An empty floor, measured later", detail: "The floor and the field come from the robots' spins once the stations are mounted." },
  { value: "size", title: "A floor of a known size", detail: "You measured the room: its width and height, from the corner that will be zero." },
  { value: "spin", title: "Around a spin already done", detail: "A spin calibration in its own frame: the floor goes round the robots that spun." },
];

const NewSiteForm: React.FC<{
  list: SiteList | null;
  spinId?: string | null;
  onDone: () => void;
}> = ({ list, spinId, onDone }) => {
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [start, setStart] = useState<NewSiteStart>(spinId ? "spin" : "empty");
  const [size, setSize] = useState("");
  const [calibration, setCalibration] = useState(spinId ?? "");
  const [persist, setPersist] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const problem = siteNameProblem(name, list?.sites.map((s) => s.name) ?? []);
  const floor = parseFloorSize(size);
  const ready = !!name && !problem && (start !== "size" || !!floor) && (start !== "spin" || !!calibration.trim());
  const file = `${list?.home ?? "~/.dotbot/sites"}/${name || "<name>"}/site.toml`;
  const submit = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError("");
    try {
      await createSite({ name, note, start, size_mm: start === "size" ? floor : null, calibration: start === "spin" ? calibration.trim() : null, persist });
      onDone();
    } catch (e) {
      setError((e as Error).message.replace(/^\d+: /, ""));
      setBusy(false);
    }
  };
  return (
    <div data-testid="new-site">
      <span className="lbl">Name</span>
      <div className={`fld${problem ? " bad" : ""}`}>
        <input aria-label="Site name" autoFocus placeholder="bench-b" value={name} maxLength={40} onChange={(e) => setName(e.target.value.trim())} onKeyDown={(e) => e.key === "Enter" && submit()} />
      </div>
      <div className="note" style={{ color: problem ? "var(--err)" : undefined }}>
        {problem || `Up to ${SITE_NAME_MAX} letters, digits, - and _: robots receive it with every calibration.`}
      </div>
      <span className="lbl" style={{ marginTop: 10 }}>
        Where zero is, in words
      </span>
      <div className="fld">
        <input aria-label="Note on zero" placeholder="the corner by the door, at the tape cross" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      <div className="note">How someone else finds zero in the room. It can be written later.</div>
      <span className="lbl" style={{ marginTop: 10 }}>
        Start from
      </span>
      <div role="radiogroup" aria-label="Start from" style={{ display: "grid", gap: 6 }}>
        {STARTS.map((s) => (
          <label key={s.value} className={`choice${start === s.value ? " on" : ""}`}>
            <input type="radio" name="start" value={s.value} checked={start === s.value} onChange={() => setStart(s.value)} />
            <span>
              <b>{s.title}</b>
              <span className="s">{s.detail}</span>
              {start === "size" && s.value === "size" && (
                <span className="fld" style={{ marginTop: 6 }}>
                  <input aria-label="Floor size" placeholder="3000 x 2000 mm" value={size} onChange={(e) => setSize(e.target.value)} />
                </span>
              )}
              {start === "spin" && s.value === "spin" && (
                <span className="fld" style={{ marginTop: 6 }}>
                  <input aria-label="Spin calibration" placeholder="its id or tag" value={calibration} onChange={(e) => setCalibration(e.target.value)} />
                </span>
              )}
            </span>
          </label>
        ))}
      </div>
      <label className="note" style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 10 }}>
        <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} /> Also use it when the controller next starts
      </label>
      <div className="infile" style={{ marginTop: 10 }}>
        <div className="ih">
          <Icon name="file" size={12} /> WRITES
        </div>
        <pre>{file}</pre>
      </div>
      {start === "spin" && (
        <div className="note" style={{ marginTop: 6 }}>
          Same as <span className="mono">dotbot site init {name || "<name>"} --from-calibration {calibration.trim() || "<id>"}</span>
        </div>
      )}
      {error && (
        <div className="callout err" style={{ marginTop: 8 }} role="alert">
          {error}
        </div>
      )}
      <footer>
        <span className="note" style={{ flex: 1 }}>
          The controller switches to it at once; robots keep what they hold.
        </span>
        <button type="button" className="btn primary" disabled={!ready || busy} onClick={submit} data-testid="new-site-create">
          {busy ? "Writing…" : "Create and open"}
        </button>
      </footer>
    </div>
  );
};

const SiteSwitch: React.FC<{ list: SiteList | null; onDone: () => void }> = ({ list, onDone }) => {
  const [persist, setPersist] = useState(false);
  const [error, setError] = useState("");
  if (!list) return <div className="note">Reading the sites…</div>;
  const others = list.sites.filter((s) => !s.current);
  return (
    <div data-testid="site-switch">
      {others.length === 0 && <div className="note">No other site pack beside this one or in ~/.dotbot/sites.</div>}
      {list.sites.map((s) => (
        <div className="orow" key={s.name} style={{ marginLeft: 0, alignItems: "flex-start", padding: "8px 4px" }}>
          <Icon name="pin" size={14} />
          <span style={{ flex: 1, minWidth: 0 }}>
            <b className="mono">{s.name}</b>
            <span className="s" style={{ display: "block" }}>
              {s.error ? s.error : `${s.extent_mm ? `${s.extent_mm[0]} × ${s.extent_mm[1]} mm` : "floor not measured"} · ${s.areas ?? 0} area(s)${s.anchor ? ` · zero: ${s.anchor}` : ""}`}
            </span>
            <span className="s mono" style={{ display: "block" }}>
              {s.shown_path}
            </span>
          </span>
          {s.current ? (
            <span className="badge">in use</span>
          ) : (
            <button
              type="button"
              className="btn xs"
              disabled={!!s.error}
              onClick={() =>
                switchSite(s.name, persist).then(onDone, (e: Error) => setError(e.message.replace(/^\d+: /, "")))
              }
            >
              Use
            </button>
          )}
        </div>
      ))}
      <label className="note" style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8 }}>
        <input type="checkbox" checked={persist} onChange={(e) => setPersist(e.target.checked)} /> Also when the controller next starts
      </label>
      <div className="note">The calibration served stays only if it is in the other site's frame; robots keep what they hold.</div>
      {error && (
        <div className="callout err" style={{ marginTop: 8 }} role="alert">
          {error}
        </div>
      )}
    </div>
  );
};

/** The New site and Switch site sheet; `onDone` runs once the controller
 * took the site. */
export const SitesSheet: React.FC<{ tab: "new" | "switch"; spinId?: string | null; onClose: () => void; onDone: () => void }> = ({ tab: first, spinId, onClose, onDone }) => {
  const [tab, setTab] = useState(first);
  const [list, setList] = useState<SiteList | null>(null);
  useEffect(() => {
    fetchSites().then(setList, () => setList({ current: "", has_pack: false, home: "~/.dotbot/sites", sites: [] }));
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Sites" data-testid="sites-sheet">
        <h2>
          <Icon name="pin" size={16} /> {tab === "new" ? "New site" : "Switch site"}
          <span className="sp" style={{ flex: 1 }} />
          <button type="button" className="btn icon ghost" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </h2>
        <div className="seg" role="tablist" style={{ marginBottom: 12 }}>
          <button type="button" role="tab" aria-selected={tab === "new"} className={tab === "new" ? "on" : ""} onClick={() => setTab("new")}>
            New
          </button>
          <button type="button" role="tab" aria-selected={tab === "switch"} className={tab === "switch" ? "on" : ""} onClick={() => setTab("switch")}>
            Switch{list ? ` · ${list.sites.length}` : ""}
          </button>
        </div>
        {tab === "new" ? <NewSiteForm list={list} spinId={spinId} onDone={onDone} /> : <SiteSwitch list={list} onDone={onDone} />}
      </div>
    </>
  );
};

/** What the editor shows when the controller has no site pack: start one,
 * or pick one already on this machine. */
export const StartScreen: React.FC<{ siteName: string; spinId?: string | null; editable: boolean; onDone: () => void }> = ({ siteName, spinId, editable, onDone }) => {
  const [list, setList] = useState<SiteList | null>(null);
  useEffect(() => {
    fetchSites().then(setList, () => setList({ current: "", has_pack: false, home: "~/.dotbot/sites", sites: [] }));
  }, []);
  return (
    <div className="start" data-testid="start-screen">
      <div className="card start-card">
        <h1>A new room</h1>
        <p className="lead">
          This controller runs {siteName ? <>with site <b className="mono">{siteName}</b>, which has no site pack</> : "with no site"}: there is no floor, field or station to edit yet. A site pack holds
          them, one folder per room.
        </p>
        <ol className="steps-list">
          <li>
            <b>Name the room</b> and say where zero is.
          </li>
          <li>
            <b>Mount two stations</b> at opposite corners, outside the floor, high enough to see all of it.
          </li>
          <li>
            <b>Spin robots in the console</b>: the circles they trace measure the stations.
          </li>
          <li>
            <b>Place the spin in the room</b>, from two robots on taped marks or from typed numbers, then serve and push it.
          </li>
        </ol>
        {editable ? (
          <NewSiteForm list={list} spinId={spinId} onDone={onDone} />
        ) : (
          <div className="callout">A new site is written from the controller's own machine, at 127.0.0.1.</div>
        )}
      </div>
      {list && list.sites.length > 0 && (
        <div className="card start-card">
          <h2 style={{ margin: "0 0 8px", fontSize: 14 }}>Or use a site already on this machine</h2>
          <SiteSwitch list={list} onDone={onDone} />
        </div>
      )}
    </div>
  );
};

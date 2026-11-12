import React, { useEffect, useState } from "react";

import { Badge } from "../shared/Badge";
import { openInEditor, parseSite, previewSite } from "./api";
import { fullDiff } from "./diff";
import { Icon } from "./icons";
import { siteModel, type Doc } from "./model";
import type { EditorSite } from "./types";

// The File view: site.toml as Save would write it, with what the draft
// changes marked. It can be edited here, or in the user's own editor while
// the page follows the file.

/** One line of TOML, coloured: table headers, strings, comments. */
export function TomlLine({ text }: { text: string }) {
  const hash = text.search(/#(?=(?:[^"]*"[^"]*")*[^"]*$)/);
  const code = hash >= 0 ? text.slice(0, hash) : text;
  const comment = hash >= 0 ? text.slice(hash) : "";
  const parts: React.ReactNode[] = [];
  if (/^\s*\[/.test(code)) parts.push(<span key="t" className="tbl">{code}</span>);
  else
    code.split(/("(?:[^"\\]|\\.)*")/).forEach((p, i) =>
      parts.push(
        p.startsWith('"') ? (
          <span key={i} className="str">
            {p}
          </span>
        ) : (
          p
        ),
      ),
    );
  if (comment) parts.push(<span key="c" className="com">{comment}</span>);
  return <>{parts}</>;
}

export interface FileViewProps {
  doc: Doc;
  /** site.toml on disk. */
  baseText: string;
  /** The hand-edited text the draft is patched onto, if any. */
  text: string | null;
  shownPath: string;
  editable: boolean;
  /** Takes a hand edit into the draft: its text and the site it reads as. */
  onText: (text: string, site: EditorSite) => void;
  /** Leaves the hand edit, back to the file with the plan's edits. */
  onDropText: () => void;
}

export const FileView: React.FC<FileViewProps> = ({ doc, baseText, text, shownPath, editable, onText, onDropText }) => {
  const [after, setAfter] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editError, setEditError] = useState("");
  const [opened, setOpened] = useState("");

  useEffect(() => {
    let live = true;
    previewSite(siteModel(doc), text).then(
      (r) => live && (setAfter(r.text), setProblem("")),
      (e: Error) => live && setProblem(e.message.replace(/^\d+: /, "")),
    );
    return () => {
      live = false;
    };
  }, [doc, text]);

  const lines = fullDiff(baseText, after ?? baseText);
  const changed = lines.filter((l) => l.op !== " ").length;
  let no = 0;

  const apply = async () => {
    if (editing === null) return;
    try {
      const { site } = await parseSite(editing);
      onText(editing, site);
      setEditing(null);
      setEditError("");
    } catch (e) {
      setEditError((e as Error).message.replace(/^\d+: /, ""));
    }
  };

  return (
    <div className="fview" data-testid="file-view">
      <div className="fhd">
        <b>site.toml</b>
        <span>{shownPath}</span>
        <span className="sp" style={{ flex: 1 }} />
        {changed > 0 && <Badge tone="warn">{changed} line{changed === 1 ? "" : "s"} pending</Badge>}
        {text !== null && <Badge tone="warn">edited by hand</Badge>}
      </div>
      {editable && (
        <div className="acts" style={{ marginTop: 0, marginBottom: 8 }}>
          {editing === null ? (
            <button type="button" className="btn sm" onClick={() => setEditing(after ?? baseText)} data-testid="file-edit">
              <Icon name="file" size={13} /> Edit here
            </button>
          ) : (
            <>
              <button type="button" className="btn sm primary" onClick={apply} data-testid="file-apply">
                Use this text
              </button>
              <button type="button" className="btn sm" onClick={() => (setEditing(null), setEditError(""))}>
                Cancel
              </button>
            </>
          )}
          <button
            type="button"
            className="btn sm"
            onClick={() =>
              openInEditor().then(
                (r) => setOpened(`Opened with ${r.command}. Save there and this page reloads the file, re-applying your draft on top.`),
                (e: Error) => setOpened(`Could not open an editor: ${e.message.replace(/^\d+: /, "")}`),
              )
            }
          >
            <Icon name="ext" size={13} /> Open in your editor
          </button>
          {text !== null && editing === null && (
            <button type="button" className="btn sm ghost" onClick={onDropText}>
              Drop the hand edit
            </button>
          )}
        </div>
      )}
      {opened && <div className="note" role="status" style={{ marginBottom: 8 }}>{opened}</div>}
      {problem && (
        <div className="callout err" role="alert" style={{ marginBottom: 8 }}>
          <div className="h">
            <Icon name="err" size={14} /> site.toml would refuse the draft
          </div>
          {problem}
        </div>
      )}
      {editing !== null ? (
        <>
          <div className="code">
            <textarea aria-label="site.toml" spellCheck={false} value={editing} onChange={(e) => setEditing(e.target.value)} onKeyDown={(e) => e.key === "Escape" && e.stopPropagation()} />
          </div>
          {editError && (
            <div className="callout err" role="alert" style={{ marginTop: 8 }}>
              <div className="h">
                <Icon name="err" size={14} /> This text does not read as a site
              </div>
              {editError}
            </div>
          )}
        </>
      ) : (
        <div className="code" data-testid="file-code">
          {lines.map((l, i) => {
            if (l.op !== "-") no++;
            return (
              <div key={i} className={`ln${l.op === "+" ? " add" : l.op === "-" ? " del" : ""}`}>
                <span className="no">{l.op === "-" ? "" : no}</span>
                <span className="g">{l.op === " " ? "" : l.op}</span>
                <span className="tx">
                  <TomlLine text={l.text} />
                </span>
              </div>
            );
          })}
        </div>
      )}
      <div className="note" style={{ marginTop: 8 }}>
        Comments, blank lines and key order are kept on Save. Edited in another editor, the file is reloaded here and your draft re-applied on top.
      </div>
    </div>
  );
};

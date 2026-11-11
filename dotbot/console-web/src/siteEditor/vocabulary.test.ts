import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";

// The page uses the data model's words (site, extent, frame, anchor, areas,
// stations, coverage, tag); these older ones must not come back in its text.
const FORBIDDEN: [string, RegExp][] = [
  ["fence", /fence/i],
  ["box", / box(es)?\b/i],
  ["Floor as a label", /^Floor\b/],
  ["valid area", /valid area/i],
];

// String literals that are code, not text: class names, test ids, keys
const ALLOWED = new Set<string>([]);

const DIR = __dirname;

function texts(file: string): { line: number; text: string }[] {
  const src = readFileSync(join(DIR, file), "utf8");
  const sf = ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const out: { line: number; text: string }[] = [];
  const visit = (n: ts.Node) => {
    let text: string | null = null;
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n) || ts.isTemplateMiddle(n) || ts.isTemplateTail(n)) text = n.text;
    else if (ts.isJsxText(n)) text = n.text;
    if (text?.trim() && !ts.isImportDeclaration(n.parent)) out.push({ line: sf.getLineAndCharacterOfPosition(n.getStart()).line + 1, text });
    ts.forEachChild(n, visit);
  };
  visit(sf);
  return out;
}

describe("the editor's words", () => {
  const files = readdirSync(DIR).filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f));

  it("reads every source file of the editor", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(FORBIDDEN)("never says %s", (_, re) => {
    const hits = files.flatMap((f) => texts(f).filter((t) => (re.test(t.text) || re.test(t.text.trim())) && !ALLOWED.has(t.text.trim())).map((t) => `${f}:${t.line}: ${t.text.trim()}`));
    expect(hits).toEqual([]);
  });
});

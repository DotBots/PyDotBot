import { describe, expect, it } from "vitest";

import {
  MAP_MODIFIER,
  SHORTCUT_GROUPS,
  holds,
  isModifier,
  modifierLabel,
  roleOf,
  typingIn,
} from "./shortcuts";

const keys = (over: Partial<Parameters<typeof roleOf>[0]> = {}) => ({
  shiftKey: false,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  ...over,
});

describe("the modifier table", () => {
  it("gives every role its own modifier", () => {
    const assigned = Object.values(MAP_MODIFIER);
    expect(new Set(assigned).size).toBe(assigned.length);
  });

  it("names the role a held modifier asks for, and none for a bare press", () => {
    expect(roleOf(keys())).toBeNull();
    expect(roleOf(keys({ shiftKey: true }))).toBe("select");
    expect(roleOf(keys({ ctrlKey: true }))).toBe("zoom");
    expect(roleOf(keys({ altKey: true }))).toBe("waypoint");
  });

  it("reads the Command key as Ctrl, for a Mac", () => {
    expect(holds(keys({ metaKey: true }), "ctrl")).toBe(true);
    expect(roleOf(keys({ metaKey: true }))).toBe("zoom");
  });

  it("resolves two modifiers in the table's order", () => {
    expect(roleOf(keys({ altKey: true, shiftKey: true }))).toBe("waypoint");
    expect(roleOf(keys({ shiftKey: true, ctrlKey: true }))).toBe("zoom");
  });
});

describe("the shortcut rows", () => {
  it("name only modifiers the table assigns", () => {
    for (const group of SHORTCUT_GROUPS) {
      for (const row of group.rows) {
        for (const key of row.keys) {
          if (isModifier(key)) expect(Object.values(MAP_MODIFIER)).toContain(key);
        }
      }
    }
  });

  it("cover every role the map answers to", () => {
    const named = new Set(
      SHORTCUT_GROUPS.flatMap((g) => g.rows.flatMap((r) => r.keys.filter(isModifier))),
    );
    for (const modifier of Object.values(MAP_MODIFIER)) expect(named.has(modifier)).toBe(true);
  });

  it("print the platform's own key names", () => {
    expect(modifierLabel("ctrl", true)).toContain("⌘");
    expect(modifierLabel("ctrl", false)).toBe("Ctrl");
    expect(modifierLabel("alt", true)).toContain("⌥");
    expect(modifierLabel("alt", false)).toBe("Alt");
    expect(modifierLabel("shift", false)).toBe("Shift");
  });
});

describe("where a key press is typing", () => {
  const el = (tag: string) => document.createElement(tag);

  it("is any field that takes text, or a choice", () => {
    expect(typingIn(el("input"))).toBe(true);
    expect(typingIn(el("textarea"))).toBe(true);
    expect(typingIn(el("select"))).toBe(true);
  });

  it("is anything editable", () => {
    const div = el("div");
    Object.defineProperty(div, "isContentEditable", { value: true });
    expect(typingIn(div)).toBe(true);
  });

  it("is not a button, the page, or nothing at all", () => {
    expect(typingIn(el("button"))).toBe(false);
    expect(typingIn(document.body)).toBe(false);
    expect(typingIn(null)).toBe(false);
  });
});

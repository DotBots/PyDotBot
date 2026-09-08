import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Controls, TextInput } from "./Controls";
import { actionMessage, controlMessage, goalsMessage, rectsMessage, textMessage } from "./messages";
import type { ControlDecl } from "./types";

const every: ControlDecl[] = [
  { id: "speed", type: "slider", min: 0, max: 100, value: 60, unit: "%" },
  { id: "wander", type: "toggle", value: true, label: "Wander when idle" },
  { id: "go", type: "button", label: "Go" },
  { id: "figure", type: "select", options: ["ring", "spiral"], value: "spiral" },
  { id: "word", type: "text", value: "DOTBOT", placeholder: "a word" },
  { id: "bot", type: "botpicker", label: "Bot" },
];

const render = (node: React.ReactElement) => renderToStaticMarkup(node);

describe("Controls", () => {
  it("renders a widget for every declared control type", () => {
    const html = render(
      <Controls
        controls={every}
        values={{}}
        onChange={() => {}}
        onAction={() => {}}
        botPicker={<div>bot 0</div>}
      />,
    );
    expect(html).toContain('type="range"');
    expect(html).toContain("Wander when idle");
    expect(html).toContain(">Go</button>");
    expect(html).toContain("<select");
    expect(html).toContain('value="spiral"');
    expect(html).toContain('type="text"');
    expect(html).toContain("bot 0");
  });

  it("shows the current value over the declared one", () => {
    const html = render(
      <Controls
        controls={every}
        values={{ speed: 12, word: "HELLO", figure: "ring" }}
        onChange={() => {}}
        onAction={() => {}}
      />,
    );
    expect(html).toContain('value="12"');
    expect(html).toContain('value="HELLO"');
    expect(html).toContain("12 %");
  });

  it("labels a control from its id when the script named none", () => {
    const html = render(
      <Controls controls={every} values={{}} onChange={() => {}} onAction={() => {}} />,
    );
    expect(html).toContain("Speed");
    expect(html).toContain("Figure");
  });

  it("says so when an app declares no controls", () => {
    const html = render(
      <Controls
        controls={[]}
        values={{}}
        onChange={() => {}}
        onAction={() => {}}
        emptyNote="The map is the input."
      />,
    );
    expect(html).toContain("The map is the input.");
  });

  it("gives a text-input app a field and one Go", () => {
    const html = render(<TextInput onSend={() => {}} />);
    expect(html).toContain('type="text"');
    expect(html).toContain(">Go</button>");
  });
});

describe("the /in wire shapes", () => {
  it("names every kind a script parses", () => {
    expect(controlMessage("speed", 40)).toEqual({ kind: "control", id: "speed", value: 40 });
    expect(actionMessage("go")).toEqual({ kind: "action", id: "go" });
    expect(textMessage("DOTBOT")).toEqual({ kind: "text", text: "DOTBOT" });
    expect(goalsMessage([{ id: 1, x: 10, y: 20 }])).toEqual({
      kind: "goals",
      points: [{ x: 10, y: 20 }],
    });
    expect(rectsMessage([{ id: 1, x: 0, y: 0, w: 100, h: 50 }])).toEqual({
      kind: "rects",
      rects: [{ x: 0, y: 0, w: 100, h: 50 }],
    });
  });

  it("sends the page's ids nowhere: a script sees only geometry", () => {
    const message = goalsMessage([{ id: 7, x: 1, y: 2 }]) as { points: object[] };
    expect(message.points[0]).not.toHaveProperty("id");
  });
});

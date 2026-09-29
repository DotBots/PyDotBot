import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { pressable } from "./pressable";

describe("pressable", () => {
  it("is a focusable button pressed by a click, Enter or Space, not other keys", () => {
    const onPress = vi.fn();
    render(<span {...pressable(onPress)}>Clear all</span>);
    const el = screen.getByRole("button", { name: "Clear all" });
    expect(el.tabIndex).toBe(0);
    fireEvent.click(el);
    fireEvent.keyDown(el, { key: "Enter" });
    fireEvent.keyDown(el, { key: " " });
    fireEvent.keyDown(el, { key: "a" });
    expect(onPress).toHaveBeenCalledTimes(3);
  });
});

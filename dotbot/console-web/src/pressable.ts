import type React from "react";

/** Props that make a non-button element a keyboard-reachable button: focusable, and pressed by Enter or Space. */
export function pressable(onPress: () => void): {
  role: "button";
  tabIndex: 0;
  onClick: () => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
} {
  return {
    role: "button",
    tabIndex: 0,
    onClick: onPress,
    onKeyDown: (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onPress();
      }
    },
  };
}

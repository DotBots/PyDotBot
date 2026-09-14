import "@testing-library/jest-dom/vitest";

// jsdom ships no ResizeObserver, and the map measures its canvas with one.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= NoopResizeObserver as unknown as typeof ResizeObserver;

// jsdom ships no pointer capture either, and the map takes it on every press.
Element.prototype.setPointerCapture ??= () => {};
Element.prototype.releasePointerCapture ??= () => {};
Element.prototype.hasPointerCapture ??= () => false;

// Nor a PointerEvent: without one a fired pointer event is a bare Event that
// carries no position and no modifier keys. A MouseEvent carries both.
if (typeof globalThis.PointerEvent === "undefined") {
  class PointerEventShim extends MouseEvent {
    pointerId: number;
    pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  globalThis.PointerEvent = PointerEventShim as unknown as typeof PointerEvent;
}

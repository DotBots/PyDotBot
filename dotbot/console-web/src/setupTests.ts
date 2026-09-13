import "@testing-library/jest-dom/vitest";

// jsdom ships no ResizeObserver, and the map measures its canvas with one.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??= NoopResizeObserver as unknown as typeof ResizeObserver;

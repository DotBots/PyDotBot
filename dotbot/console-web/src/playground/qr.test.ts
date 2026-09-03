import { describe, expect, it } from "vitest";

import { isLoopbackHost, loopbackHint, phoneUrl } from "./qr";

describe("phoneUrl", () => {
  it("keeps the origin and path and rebuilds the query", () => {
    const url = phoneUrl("http://192.168.1.20:5173/playground/?world=fake&theme=light#x", {
      world: "controller",
      app: "follow",
    });
    expect(url).toBe("http://192.168.1.20:5173/playground/?world=controller&app=follow");
  });

  it("drops absent and empty values", () => {
    const url = phoneUrl("http://host/playground/", {
      world: "controller",
      n: undefined,
      app: "",
    });
    expect(url).toBe("http://host/playground/?world=controller");
  });
});

describe("isLoopbackHost", () => {
  it("knows the hosts a phone cannot reach", () => {
    expect(isLoopbackHost("localhost")).toBe(true);
    expect(isLoopbackHost("127.0.0.1")).toBe(true);
    expect(isLoopbackHost("[::1]")).toBe(true);
    expect(isLoopbackHost("192.168.1.20")).toBe(false);
  });
});

describe("loopbackHint", () => {
  it("names the controller's bind flag when the controller serves the page", () => {
    const hint = loopbackHint("/console/playground/");
    expect(hint.flag).toBe("--controller-http-host 0.0.0.0");
    expect(hint.lead).toContain("Restart the simulator or the controller with");
  });

  it("names vite's flag when the dev server serves it", () => {
    const hint = loopbackHint("/playground/");
    expect(hint.flag).toBe("--host");
    expect(hint.lead).toContain("Start vite with");
  });

  it("says the same thing about why the URL fails either way", () => {
    for (const path of ["/console/playground/", "/playground/"]) {
      expect(loopbackHint(path).lead).toContain("only resolves on this machine");
    }
  });
});

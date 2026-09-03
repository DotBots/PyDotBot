import { describe, expect, it } from "vitest";

import { isLoopbackHost, phoneUrl } from "./qr";

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

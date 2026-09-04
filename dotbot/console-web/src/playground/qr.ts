// The URL a phone should open, and whether a QR of it is worth showing.

/**
 * The page's own origin and path, with the query rebuilt from what the page is
 * showing now rather than from what its own URL happened to carry. Empty and
 * absent values are dropped, and so is the hash.
 */
export function phoneUrl(href: string, query: Record<string, string | undefined>): string {
  const url = new URL(href);
  const wanted = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") wanted.set(key, value);
  }
  url.search = wanted.toString();
  url.hash = "";
  return url.toString();
}

/**
 * A host only this machine can reach. A QR of such a URL scans fine and then
 * fails on the phone, so the card says so instead of pretending.
 */
export function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

/** The sentence the card shows, split so the flag can be set in mono. */
export interface LoopbackHint {
  lead: string;
  flag: string;
  tail: string;
}

/**
 * How to make the page reachable from a phone, which depends on who is
 * serving it: the controller mounts the built bundle under `/console/`, and
 * binds to loopback unless told otherwise; the vite dev server serves
 * `/playground/` from the source tree.
 */
export function loopbackHint(pathname: string): LoopbackHint {
  const lead = "This URL only resolves on this machine, so a phone cannot open it. ";
  if (pathname.startsWith("/console/")) {
    return {
      lead: `${lead}Restart the simulator or the controller with `,
      flag: "--controller-http-host 0.0.0.0",
      tail: ", then open the page on this machine's address on the network.",
    };
  }
  return {
    lead: `${lead}Start vite with `,
    flag: "--host",
    tail: ", then reload the page on the address it prints.",
  };
}

// The designated control-plane image: the one that speaks DBP, so flashing it
// is how a bot becomes drivable again.
//
// A setting rather than a choice - one slot, set once, no history. Kept in
// localStorage, which is right for one operator at a bench and wrong for a
// shared testbed: a fleet's recovery image should not live in one person's
// browser. Moving it server-side is a separate piece of work, and is the same
// boundary the operator-vs-user permission question runs along.

import { FirmwareFile } from "./firmwareFile";

const KEY = "dotbot.console.controlPlaneImage.v1";

export function load(): FirmwareFile | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const e = JSON.parse(raw);
    if (
      e &&
      typeof e.name === "string" &&
      typeof e.b64 === "string" &&
      typeof e.lastModified === "number"
    ) {
      return e;
    }
    return null;
  } catch {
    return null; // unparseable or storage blocked: no image designated
  }
}

export function save(image: FirmwareFile | null): FirmwareFile | null {
  try {
    if (image === null) window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, JSON.stringify(image));
  } catch {
    /* quota or private mode: the picker still works, it just is not remembered */
  }
  return image;
}

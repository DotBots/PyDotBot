// Reading a firmware image out of a file input.
//
// swarmit takes the image as base64 in the request body, so the file never
// touches the server's filesystem and any .bin the operator can see is
// flashable. The browser cannot re-read a path later, so whatever is captured
// here is all we will ever have of that file.

export interface FirmwareFile {
  name: string;
  b64: string;
  /** The source file's own mtime, i.e. when it was built. */
  lastModified: number;
}

/** Base64 without blowing the argument limit on a multi-hundred-kB image. */
export function toBase64(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

/** Decoded byte length of a base64 payload, for display. */
export function decodedSize(b64: string): number {
  if (!b64) return 0;
  const pad = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor((b64.length * 3) / 4) - pad);
}

export async function readFirmwareFile(file: File): Promise<FirmwareFile> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.length === 0) throw new Error("file is empty");
  return { name: file.name, b64: toBase64(bytes), lastModified: file.lastModified };
}

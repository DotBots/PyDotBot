// What a typed length or angle means: "1.2m", "43cm", "430", "430 mm",
// and "+50" or "-20" relative to the value already there.

export type Parsed = { value: number } | { error: string };

const LENGTH_UNITS: Record<string, number> = { mm: 1, cm: 10, m: 1000 };

const NUMBER = /^([+-])?\s*(\d+(?:[.,]\d*)?|[.,]\d+)\s*([a-zA-Z°]*)$/;

function parse(text: string, current: number, units: Record<string, number>, fallback: string): Parsed {
  const t = text.trim();
  if (!t) return { error: "type a number" };
  const m = NUMBER.exec(t);
  if (!m) return { error: `not a ${fallback === "mm" ? "length" : "number"}: try 1.2m, 43cm or +50` };
  const [, sign, digits, unitRaw] = m;
  const unit = (unitRaw || fallback).toLowerCase();
  const scale = units[unit];
  if (scale === undefined) return { error: `unknown unit "${unitRaw}": use ${Object.keys(units).join(", ")}` };
  const n = Number(digits.replace(",", ".")) * scale;
  if (!Number.isFinite(n)) return { error: "type a number" };
  if (sign === "+") return { value: current + n };
  if (sign === "-") return { value: current - n };
  return { value: n };
}

/** A length in mm, rounded to 0.1 mm. */
export function parseMm(text: string, current: number): Parsed {
  const p = parse(text, current, LENGTH_UNITS, "mm");
  return "value" in p ? { value: Math.round(p.value * 10) / 10 } : p;
}

/** An angle in degrees. */
export function parseDeg(text: string, current: number): Parsed {
  const p = parse(text, current, { "°": 1, deg: 1, rad: 180 / Math.PI }, "deg");
  return "value" in p ? { value: Math.round(p.value * 100) / 100 } : p;
}

/** A length as the fields show it: whole mm, or one decimal when it has one. */
export const showMm = (v: number) => String(Math.round(v * 10) / 10);

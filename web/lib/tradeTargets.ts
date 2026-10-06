export interface GraduatedTargets {
  t1: number;
  t2: number;
  t3: number;
}

function cents(value: number): number {
  return Math.round(value * 100);
}

function fromCents(value: number): number {
  return value / 100;
}

function price(value: number | string | null | undefined): number | null {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number) && number > 0 ? number : null;
}

/**
 * Three long targets from the displayed entry and stop.
 * Risk is entry − stop. Stations are 1R, 2R and 3R.
 * A real resistance above entry replaces a station only when it falls in that station's band.
 */
export function graduatedTargets(
  entry: number | string | null | undefined,
  stop: number | string | null | undefined,
  resistances: Array<number | null | undefined> = [],
): GraduatedTargets | null {
  const entryPrice = price(entry);
  const stopPrice = price(stop);
  if (entryPrice == null || stopPrice == null || !(entryPrice > stopPrice)) return null;
  const entryCents = cents(entryPrice);
  const risk = entryCents - cents(stopPrice);
  if (risk <= 0) return null;
  const at = (multiple: number) => fromCents(entryCents + multiple * risk);
  const levels = resistances
    .map((level) => price(level))
    .filter((level): level is number => level != null && level > entryPrice)
    .sort((left, right) => left - right);

  const picked: number[] = [];
  for (const multiple of [1, 2, 3]) {
    const prior = picked.length ? picked[picked.length - 1] : entryPrice;
    const span = risk / 100;
    const floor = multiple === 1 ? prior : entryPrice + (multiple - 0.5) * span;
    const cap = entryPrice + (multiple === 3 ? 6 : multiple + 0.5) * span;
    const hit = levels.find((level) => level > prior && level >= floor && level <= cap);
    const next = hit != null ? fromCents(cents(hit)) : at(multiple);
    picked.push(next > prior ? next : at(multiple));
  }
  return { t1: picked[0], t2: picked[1], t3: picked[2] };
}

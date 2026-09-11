export const RIZG_BG = "#0F1218";
export const RIZG_INK = "#E8EAED";
export const RIZG_INK_SOFT = "#C5CAD3";
export const RIZG_ACCENT = "#00E676";

/** Geometric R + Arabic ر as one rising stroke. ViewBox 0 0 128 128. */
export const RIZG_MONOGRAM_PATH =
  "M38 98V32h24c19 0 30 11 30 23.5 0 9.5-6.5 17.8-17 21.2 14-4.5 27.5-23 34-43.2";

export function rizgMarkSvg({
  rounded = false,
  size = 128,
}: {
  rounded?: boolean;
  size?: number;
} = {}): string {
  const rx = rounded ? 32 : 0;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="${size}" height="${size}" fill="none">
  <rect width="128" height="128" rx="${rx}" fill="${RIZG_BG}"/>
  <defs>
    <linearGradient id="rizgSilver" x1="30" y1="24" x2="108" y2="100" gradientUnits="userSpaceOnUse">
      <stop stop-color="#F8FAFC"/>
      <stop offset=".5" stop-color="${RIZG_INK_SOFT}"/>
      <stop offset="1" stop-color="${RIZG_INK}"/>
    </linearGradient>
  </defs>
  <path d="${RIZG_MONOGRAM_PATH}" stroke="url(#rizgSilver)" stroke-width="12.5" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="110" cy="31" r="7" fill="${RIZG_ACCENT}"/>
</svg>`;
}

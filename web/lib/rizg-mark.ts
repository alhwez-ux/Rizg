export const RIZG_BG = "#0B0F19";
export const RIZG_INK = "#F8FAFC";
export const RIZG_ACCENT = "#00E676";
export const RIZG_SIZE = 48;
export const RIZG_CORNER_RADIUS = 12;
export const RIZG_STROKE_WIDTH = 3.5;
export const RIZG_DOT = { cx: 33, cy: 15, r: 3.5 };

/** Geometric R with a rising arrow. ViewBox 0 0 48 48. */
export const RIZG_MONOGRAM_PATH =
  "M14 34V14H23C27.4183 14 31 17.5817 31 22C31 26.4183 27.4183 30 23 30H14M14 30H24L34 34";

export function rizgMarkSvg({
  rounded = false,
  size = RIZG_SIZE,
}: {
  rounded?: boolean;
  size?: number;
} = {}): string {
  const rx = rounded ? RIZG_CORNER_RADIUS : 0;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${RIZG_SIZE} ${RIZG_SIZE}" width="${size}" height="${size}" fill="none">
  <rect width="${RIZG_SIZE}" height="${RIZG_SIZE}" rx="${rx}" fill="${RIZG_BG}"/>
  <path d="${RIZG_MONOGRAM_PATH}" stroke="${RIZG_INK}" stroke-width="${RIZG_STROKE_WIDTH}" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="${RIZG_DOT.cx}" cy="${RIZG_DOT.cy}" r="${RIZG_DOT.r}" fill="${RIZG_ACCENT}"/>
</svg>`;
}

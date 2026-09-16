export const THEME_STORAGE_KEY = "rizg-theme";
export const THEME_DARK = "dark";
export const THEME_LIGHT = "light";
export const THEME_COLOR_DARK = "#0B0F19";
export const THEME_COLOR_LIGHT = "#f3f6fa";

export type DisplayTheme = typeof THEME_DARK | typeof THEME_LIGHT;

export const THEME_BOOTSTRAP = `(() => {try{var t=localStorage.getItem(${JSON.stringify(THEME_STORAGE_KEY)});if(t!=="light"&&t!=="dark")t="dark";var r=document.documentElement;r.setAttribute("data-theme",t);r.style.colorScheme=t;var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute("content",t==="light"?${JSON.stringify(THEME_COLOR_LIGHT)}:${JSON.stringify(THEME_COLOR_DARK)});}catch(e){document.documentElement.setAttribute("data-theme","dark");}})();`;

export function isDisplayTheme(value: string | null | undefined): value is DisplayTheme {
  return value === THEME_DARK || value === THEME_LIGHT;
}

export function readStoredTheme(): DisplayTheme {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (isDisplayTheme(value)) return value;
  } catch {
    /* ignore private-mode / blocked storage */
  }
  return THEME_DARK;
}

export function applyTheme(theme: DisplayTheme) {
  const root = document.documentElement;
  root.setAttribute("data-theme", theme);
  root.style.colorScheme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === THEME_LIGHT ? THEME_COLOR_LIGHT : THEME_COLOR_DARK);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* ignore private-mode / blocked storage */
  }
}

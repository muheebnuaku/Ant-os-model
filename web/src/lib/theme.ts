export type ThemeChoice = "system" | "light" | "dark";
export type Density = "compact" | "standard" | "comfortable";

const THEME_KEY = "antos.theme";
const DENSITY_KEY = "antos.density";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* preference simply won't persist */
  }
}

export function readTheme(): ThemeChoice {
  const v = read(THEME_KEY);
  return v === "light" || v === "dark" ? v : "system";
}

export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement;
  if (choice === "system") delete root.dataset.theme;
  else root.dataset.theme = choice;
  write(THEME_KEY, choice === "system" ? null : choice);
}

export function readDensity(): Density {
  const v = read(DENSITY_KEY);
  return v === "compact" || v === "comfortable" ? v : "standard";
}

export function applyDensity(density: Density): void {
  const root = document.documentElement;
  if (density === "standard") delete root.dataset.density;
  else root.dataset.density = density;
  write(DENSITY_KEY, density === "standard" ? null : density);
}

/** Runs before first paint (inlined in <head>) so saved preferences never flash. */
export const THEME_BOOT = `try{var d=document.documentElement,t=localStorage.getItem("${THEME_KEY}"),n=localStorage.getItem("${DENSITY_KEY}");if(t==="light"||t==="dark")d.dataset.theme=t;if(n==="compact"||n==="comfortable")d.dataset.density=n}catch(e){}`;

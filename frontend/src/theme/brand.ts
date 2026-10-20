// Branding lives in brand.json next to this file: the app name, the logo, and every color in light
// and dark mode. The web app and the PDF reports both read it, so it is the one file to edit.
// This file describes what each color is for and turns the colors into CSS variables.

import brandFile from "./brand.json";

export type Mode = "light" | "dark";

export interface Palette {
  /** Buttons and other filled brand elements, and the text on them. */
  brand: string;
  brandHover: string;
  onBrand: string;
  /** Links and focus rings. In dark mode this needs to be lighter than brand. */
  link: string;

  /** Page background, card background, and two quieter fills (table headers, tracks, badges). */
  canvas: string;
  surface: string;
  subtle: string;
  soft: string;
  /** Text: main, secondary, explanatory, and least important. */
  ink: string;
  ink2: string;
  muted: string;
  faint: string;
  /** Borders and dividers. */
  line: string;
  lineSoft: string;
  lineStrong: string;

  /** Sentiment. The plain color is for bars and charts; soft/mark/ink/line make chips and
   * highlights; solid is a filled chip, with onSolid text. */
  positive: string;
  positiveSoft: string;
  positiveMark: string;
  positiveInk: string;
  positiveLine: string;
  positiveSolid: string;
  negative: string;
  negativeSoft: string;
  negativeMark: string;
  negativeInk: string;
  negativeLine: string;
  negativeSolid: string;
  mixed: string;
  mixedSoft: string;
  mixedMark: string;
  mixedInk: string;
  mixedLine: string;
  mixedSolid: string;
  /** Reviews with no overall view, and other neutral chart marks. */
  neutral: string;
  onSolid: string;

  /** Notices that are neither good nor bad. */
  infoSoft: string;
  infoInk: string;
  infoLine: string;

  /** Extra series colors for charts that compare titles, in order. */
  series: string[];
}

// The chart colors in brand.json were checked for color-blind readers with the dataviz palette validator against
// each mode's card background (surface). positive/mixed/negative pass in both modes; in dark mode
// positive next to negative is just under the target, so charts that put them side by side also
// separate them by position (positive above the baseline, negative below). The series colors are
// a validated set; in light mode the 3rd and 4th, and mixed, are pale on white, so those charts
// always come with labels or a table. Re-run the validator after changing any of these.
export interface Brand {
  appName: string;
  companyName: string;
  /** Path of the logo under frontend/public. */
  logoUrl: string;
  palette: Record<Mode, Palette>;
}

export const brand: Brand = brandFile;

const kebab = (key: string) => key.replace(/([a-z])([A-Z0-9])/g, "$1-$2").toLowerCase();

function cssVars(p: Palette): string {
  return Object.entries(p)
    .filter(([, v]) => typeof v === "string")
    .map(([k, v]) => `--c-${kebab(k)}: ${v};`)
    .join(" ");
}

/** Write both palettes as CSS variables; Tailwind's color utilities read them (see index.css).
 * The <html> element's data-theme attribute picks one. */
export function applyBrand(doc: Document = document): void {
  let style = doc.getElementById("brand-colors");
  if (!style) {
    style = doc.createElement("style");
    style.id = "brand-colors";
    doc.head.appendChild(style);
  }
  const { light, dark } = brand.palette;
  style.textContent =
    `:root { ${cssVars(light)} color-scheme: light; }\n` + `:root[data-theme="dark"] { ${cssVars(dark)} color-scheme: dark; }`;
}

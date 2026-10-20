// The one file to edit for branding: name, logo, and every color in light and dark mode.
// Colors are placeholders until Midwest Games supplies its own.

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

// Chart colors were checked for color-blind readers with the dataviz palette validator against
// each mode's card background (surface). positive/mixed/negative pass in both modes; in dark mode
// positive next to negative is just under the target, so charts that put them side by side also
// separate them by position (positive above the baseline, negative below). The series colors are
// a validated set; in light mode the 3rd and 4th, and mixed, are pale on white, so those charts
// always come with labels or a table. Re-run the validator after changing any of these.
export const brand = {
  appName: "Review Insights",
  companyName: "Midwest Games",
  logoUrl: "/brand/logo.svg",
  palette: {
    light: {
      brand: "#1f4e79",
      brandHover: "#173d5f",
      onBrand: "#ffffff",
      link: "#1f4e79",
      canvas: "#f6f7f9",
      surface: "#ffffff",
      subtle: "#f8fafc",
      soft: "#eef2f6",
      ink: "#0f172a",
      ink2: "#3f4b5b",
      muted: "#64748b",
      faint: "#94a3b8",
      line: "#e2e8f0",
      lineSoft: "#f1f5f9",
      lineStrong: "#cbd5e1",
      positive: "#0e8063",
      positiveSoft: "#ebf7f3",
      positiveMark: "#cdeee3",
      positiveInk: "#0b5e49",
      positiveLine: "#a9dccb",
      positiveSolid: "#0b6e56",
      negative: "#c8442a",
      negativeSoft: "#fdf1ef",
      negativeMark: "#fadcd6",
      negativeInk: "#a3301f",
      negativeLine: "#f2c3ba",
      negativeSolid: "#a8321f",
      mixed: "#d6a52a",
      mixedSoft: "#fdf7e9",
      mixedMark: "#f8e8c2",
      mixedInk: "#80580c",
      mixedLine: "#ecd39a",
      mixedSolid: "#a8740f",
      neutral: "#cbd5e1",
      onSolid: "#ffffff",
      infoSoft: "#eef5fc",
      infoInk: "#1d4673",
      infoLine: "#c4daf0",
      series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"],
    },
    dark: {
      brand: "#2f6aa3",
      brandHover: "#3b7cbc",
      onBrand: "#ffffff",
      link: "#8bbcec",
      canvas: "#0f151b",
      surface: "#17202a",
      subtle: "#1b2530",
      soft: "#243140",
      ink: "#e6ecf1",
      ink2: "#c3ceda",
      muted: "#9aa8b5",
      faint: "#6f7e8d",
      line: "#2b3744",
      lineSoft: "#222d38",
      lineStrong: "#3c4a59",
      positive: "#12a08a",
      positiveSoft: "#122e29",
      positiveMark: "#1a4038",
      positiveInk: "#8fd9c6",
      positiveLine: "#285a4f",
      positiveSolid: "#5cc4ad",
      negative: "#d94f5c",
      negativeSoft: "#361c20",
      negativeMark: "#4f262c",
      negativeInk: "#f4a3aa",
      negativeLine: "#6b343b",
      negativeSolid: "#ec8a93",
      mixed: "#c98500",
      mixedSoft: "#33290f",
      mixedMark: "#4a3c17",
      mixedInk: "#f0cd7a",
      mixedLine: "#6b5620",
      mixedSolid: "#e6b94f",
      neutral: "#4a5866",
      onSolid: "#0f151b",
      infoSoft: "#16283a",
      infoInk: "#a9cdf2",
      infoLine: "#2b4a6b",
      series: ["#3987e5", "#d95926", "#199e70", "#c98500"],
    },
  } satisfies Record<Mode, Palette>,
};

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

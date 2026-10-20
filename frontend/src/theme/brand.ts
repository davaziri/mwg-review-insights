// The one file to edit for branding. Colors are placeholders until Midwest Games supplies its own.
export const brand = {
  appName: "Review Insights",
  companyName: "Midwest Games",
  logoUrl: "/brand/logo.svg",
  colors: {
    primary: "#1f4e79",
    primaryHover: "#173d5f",
    onPrimary: "#ffffff",
    positive: "#2e7d4f",
    negative: "#b3412e",
    mixed: "#b7862b",
  },
};

/** Expose brand colors as CSS variables; Tailwind's brand-* utilities read them (see index.css). */
export function applyBrand(root: HTMLElement = document.documentElement): void {
  const c = brand.colors;
  root.style.setProperty("--brand-primary", c.primary);
  root.style.setProperty("--brand-primary-hover", c.primaryHover);
  root.style.setProperty("--brand-on-primary", c.onPrimary);
  root.style.setProperty("--brand-positive", c.positive);
  root.style.setProperty("--brand-negative", c.negative);
  root.style.setProperty("--brand-mixed", c.mixed);
}

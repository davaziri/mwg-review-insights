import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { brand, type Mode, type Palette } from "./brand";

export type Preference = "system" | Mode;

const STORAGE_KEY = "mwg-theme";

function readPreference(): Preference {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

const systemDark = () => window.matchMedia("(prefers-color-scheme: dark)").matches;

interface ModeState {
  preference: Preference;
  mode: Mode;
  palette: Palette;
  setPreference: (p: Preference) => void;
}

const ModeContext = createContext<ModeState | null>(null);

/** Light or dark mode: follows the computer's setting unless someone picks one. */
export function ModeProvider({ children }: { children: ReactNode }) {
  const [preference, setPref] = useState<Preference>(readPreference);
  const [dark, setDark] = useState(systemDark);

  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setDark(query.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const mode: Mode = preference === "system" ? (dark ? "dark" : "light") : preference;
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    document.documentElement.style.background = brand.palette[mode].canvas;
  }, [mode]);

  const setPreference = (p: Preference) => {
    setPref(p);
    try {
      if (p === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, p);
    } catch {
      // Private windows can block storage; the choice still applies until reload.
    }
  };

  return <ModeContext.Provider value={{ preference, mode, palette: brand.palette[mode], setPreference }}>{children}</ModeContext.Provider>;
}

export function useMode(): ModeState {
  const state = useContext(ModeContext);
  if (!state) throw new Error("useMode needs a ModeProvider");
  return state;
}

/** The current palette, for charts that need actual color values. */
export function usePalette(): Palette {
  return useMode().palette;
}

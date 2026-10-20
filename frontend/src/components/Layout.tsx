import { NavLink, Outlet } from "react-router";

import { brand } from "../theme/brand";
import { useMode, type Preference } from "../theme/mode";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `shrink-0 rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-soft text-ink" : "text-ink-2 hover:text-ink"}`;

const MODES: { value: Preference; label: string; icon: string }[] = [
  { value: "system", label: "Match my computer", icon: "M4 5h16v11H4zM9 20h6M12 16v4" },
  { value: "light", label: "Light", icon: "M12 4V2M12 22v-2M4 12H2M22 12h-2M5.6 5.6 4.2 4.2M19.8 19.8l-1.4-1.4M5.6 18.4l-1.4 1.4M19.8 4.2l-1.4 1.4M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z" },
  { value: "dark", label: "Dark", icon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" },
];

function ModeSwitch() {
  const { preference, setPreference } = useMode();
  return (
    <div role="radiogroup" aria-label="Color mode" className="flex shrink-0 rounded-md border border-line p-0.5">
      {MODES.map((m) => (
        <button
          key={m.value}
          type="button"
          role="radio"
          aria-checked={preference === m.value}
          title={m.label}
          aria-label={m.label}
          onClick={() => setPreference(m.value)}
          className={`rounded p-1.5 ${preference === m.value ? "bg-soft text-ink" : "text-muted hover:text-ink"}`}
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d={m.icon} />
          </svg>
        </button>
      ))}
    </div>
  );
}

export function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2.5">
            <img src={brand.logoUrl} alt="" className="h-8 w-8" />
            <div className="leading-tight">
              <div className="text-sm font-semibold">{brand.appName}</div>
              <div className="text-xs text-muted">{brand.companyName}</div>
            </div>
          </NavLink>
          <div className="ml-auto sm:order-last">
            <ModeSwitch />
          </div>
          <nav className="-mx-1 flex w-full gap-1 overflow-x-auto px-1 sm:w-auto" aria-label="Main">
            <NavLink to="/" end className={navClass}>
              Portfolio
            </NavLink>
            <NavLink to="/compare" className={navClass}>
              Compare
            </NavLink>
            <NavLink to="/titles" end className={navClass}>
              Manage titles
            </NavLink>
            <NavLink to="/sync-log" className={navClass}>
              Sync log
            </NavLink>
            <NavLink to="/quality" className={navClass}>
              Analysis quality
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

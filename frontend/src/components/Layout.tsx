import { NavLink, Outlet } from "react-router";

import { brand } from "../theme/brand";

const navClass = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${
    isActive ? "bg-slate-100 text-slate-900" : "text-slate-600 hover:text-slate-900"
  }`;

export function Layout() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
          <div className="flex items-center gap-2.5">
            <img src={brand.logoUrl} alt="" className="h-8 w-8" />
            <div className="leading-tight">
              <div className="text-sm font-semibold">{brand.appName}</div>
              <div className="text-xs text-slate-500">{brand.companyName}</div>
            </div>
          </div>
          <nav className="flex gap-1">
            <NavLink to="/" end className={navClass}>
              Titles
            </NavLink>
            <NavLink to="/sync-log" className={navClass}>
              Sync log
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

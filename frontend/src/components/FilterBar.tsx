import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { api } from "../api/client";
import { activeFilterCount, RANGE_LABELS, readFilters, writeFilters, type PageFilters, type RangePreset } from "../lib/filters";
import { languageName } from "../lib/languages";
import { MultiSelect } from "./MultiSelect";
import { inputClass, selectClass } from "./ui";

type TriState = "any" | "true" | "false";
const tri = (v: boolean | undefined): TriState => (v === undefined ? "any" : v ? "true" : "false");
const fromTri = (v: string): boolean | undefined => (v === "any" ? undefined : v === "true");

/** One row of filters for a title. Everything on the page below it uses the same filters. */
export function FilterBar({ titleId, appId }: { titleId: number; appId: number }) {
  const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(false);
  const f = readFilters(params);
  const facets = useQuery({ queryKey: ["facets", titleId, appId], queryFn: () => api.facets(titleId, appId), staleTime: 60_000 });
  const set = (patch: Partial<PageFilters>) => setParams(writeFilters(params, { ...f, ...patch }), { replace: true });

  const dateValue = f.range ?? (f.from || f.to ? "custom" : "all");
  const onDate = (v: string) => {
    if (v === "all") set({ range: undefined, from: undefined, to: undefined });
    else if (v === "custom") set({ range: undefined, from: f.from ?? facets.data?.date_min ?? undefined, to: f.to });
    else set({ range: v as RangePreset, from: undefined, to: undefined });
  };
  const active = activeFilterCount(f);
  const langs = facets.data?.languages ?? [];
  const bands = (facets.data?.playtime_bands ?? []).filter((b) => b.count > 0 || f.playtime.includes(b.band));

  return (
    <div className="mb-5">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="mb-2 rounded-md border border-line-strong bg-surface px-3 py-1.5 text-sm font-medium sm:hidden"
      >
        {open ? "Hide filters" : active ? `Filters (${active})` : "Filters"}
      </button>
      <div className={`${open ? "flex" : "hidden"} flex-wrap items-center gap-2 sm:flex`} role="group" aria-label="Filters">
        <select aria-label="Date range" className={selectClass} value={dateValue} onChange={(e) => onDate(e.target.value)}>
          <option value="all">Dates: all time</option>
          {Object.entries(RANGE_LABELS).map(([k, label]) => (
            <option key={k} value={k}>
              Dates: {label.toLowerCase()}
            </option>
          ))}
          <option value="custom">Dates: pick a range</option>
        </select>
        {dateValue === "custom" && (
          <span className="flex items-center gap-1 text-sm text-muted">
            <input type="date" aria-label="From" className={`${inputClass} w-auto`} value={f.from ?? ""} onChange={(e) => set({ from: e.target.value || undefined })} />
            to
            <input type="date" aria-label="To" className={`${inputClass} w-auto`} value={f.to ?? ""} onChange={(e) => set({ to: e.target.value || undefined })} />
          </span>
        )}
        <select aria-label="Vote" className={selectClass} value={f.vote ?? "all"} onChange={(e) => set({ vote: e.target.value === "all" ? undefined : (e.target.value as "positive" | "negative") })}>
          <option value="all">Votes: all</option>
          <option value="positive">Votes: recommended</option>
          <option value="negative">Votes: not recommended</option>
        </select>
        <MultiSelect
          label="Playtime"
          options={bands.map((b) => ({ value: b.band, label: b.label, count: b.count }))}
          selected={f.playtime}
          onChange={(playtime) => set({ playtime })}
        />
        <MultiSelect
          label="Language"
          options={langs.map((l) => ({ value: l.code, label: languageName(l.code), count: l.count }))}
          selected={f.language}
          onChange={(language) => set({ language })}
        />
        <select aria-label="Early access" className={selectClass} value={tri(f.earlyAccess)} onChange={(e) => set({ earlyAccess: fromTri(e.target.value) })}>
          <option value="any">Written: any time</option>
          <option value="true">Written: in early access</option>
          <option value="false">Written: after release</option>
        </select>
        <select aria-label="Steam Deck" className={selectClass} value={tri(f.steamDeck)} onChange={(e) => set({ steamDeck: fromTri(e.target.value) })}>
          <option value="any">Device: any</option>
          <option value="true">Device: Steam Deck</option>
          <option value="false">Device: not Steam Deck</option>
        </select>
        <select aria-label="Developer response" className={selectClass} value={tri(f.devResponse)} onChange={(e) => set({ devResponse: fromTri(e.target.value) })}>
          <option value="any">Dev reply: any</option>
          <option value="true">Dev reply: yes</option>
          <option value="false">Dev reply: no</option>
        </select>
        {active > 0 && (
          <button
            type="button"
            onClick={() => setParams(writeFilters(params, { app: f.app, playtime: [], language: [] }), { replace: true })}
            className="rounded-md px-2 py-1.5 text-sm font-medium text-link hover:underline"
          >
            Clear {active === 1 ? "filter" : `${active} filters`}
          </button>
        )}
      </div>
    </div>
  );
}

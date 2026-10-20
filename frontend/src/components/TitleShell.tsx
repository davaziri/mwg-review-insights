import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useLocation, useOutletContext, useParams, useSearchParams } from "react-router";

import { api } from "../api/client";
import { STATUS_LABELS, type Title } from "../api/types";
import { filterSearch, readFilters, writeFilters, type PageFilters } from "../lib/filters";
import { FilterBar } from "./FilterBar";
import { Badge } from "./ui";

export interface TitleContext {
  title: Title;
  /** The Steam app being looked at: the main game, or the demo. */
  appId: number;
  filters: PageFilters;
  /** The filter part of the URL, to carry the filters along on links between the title's pages. */
  search: string;
}

export const useTitle = () => useOutletContext<TitleContext>();

/** The frame around every page of one title: header, main game or demo, tabs, and filters. */
export function TitleShell() {
  const titleId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const title = useQuery({ queryKey: ["title", titleId], queryFn: () => api.title(titleId) });

  if (title.isPending) return <p className="text-sm text-muted">Loading...</p>;
  if (title.isError) return <p className="text-sm text-negative-ink">Could not load this title: {title.error.message}</p>;

  const t = title.data;
  const main = t.apps.find((a) => !a.is_demo);
  const demo = t.apps.find((a) => a.is_demo);
  const filters = readFilters(params);
  // A title whose reviews are all on its demo (GodsTV before launch) opens on the demo.
  const defaultApp = demo && !main?.stored_reviews && demo.stored_reviews ? demo.app_id : t.steam_app_id;
  const appId = filters.app && t.apps.some((a) => a.app_id === filters.app) ? filters.app : defaultApp;
  const app = t.apps.find((a) => a.app_id === appId);
  const search = filterSearch(params);
  const onAnalysis = location.pathname.endsWith("/analysis");
  const snapshot = app?.latest_snapshot;

  const tab = ({ isActive }: { isActive: boolean }) =>
    `shrink-0 border-b-2 px-3 py-2 text-sm font-medium ${isActive ? "border-brand text-ink" : "border-transparent text-ink-2 hover:text-ink"}`;

  return (
    <div>
      <Link to="/" className="text-sm text-muted hover:underline">
        Portfolio
      </Link>
      <div className="mt-1 mb-4 flex flex-wrap items-center gap-4">
        {t.header_image_url && (
          <img src={t.header_image_url} alt="" className="h-14 w-[120px] shrink-0 rounded object-cover" onError={(e) => (e.currentTarget.style.display = "none")} />
        )}
        <div className="min-w-0 flex-1">
          <h1 className="text-xl font-semibold">{t.name}</h1>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <Badge>{STATUS_LABELS[t.status]}</Badge>
            {t.developers?.length ? <span>{t.developers.join(", ")}</span> : null}
            {snapshot?.review_score_desc && snapshot.total_reviews ? (
              <span>
                Steam: <span className="font-medium text-ink">{snapshot.review_score_desc}</span> ({snapshot.total_reviews.toLocaleString()} reviews)
              </span>
            ) : null}
            <a href={`https://store.steampowered.com/app/${appId}/`} target="_blank" rel="noreferrer" className="text-link hover:underline">
              Steam store page
            </a>
          </div>
        </div>
        {demo && (
          <div className="flex rounded-md border border-line p-0.5 text-sm" role="radiogroup" aria-label="Main game or demo">
            {[main, demo].map(
              (a) =>
                a && (
                  <button
                    key={a.app_id}
                    type="button"
                    role="radio"
                    aria-checked={appId === a.app_id}
                    onClick={() => setParams(writeFilters(params, { ...filters, app: a.app_id }))}
                    className={`rounded px-3 py-1 ${appId === a.app_id ? "bg-soft font-medium text-ink" : "text-ink-2 hover:text-ink"}`}
                  >
                    {a.is_demo ? "Demo" : "Main game"} <span className="text-muted">({a.stored_reviews.toLocaleString()})</span>
                  </button>
                ),
            )}
          </div>
        )}
      </div>

      <nav className="mb-5 flex gap-1 overflow-x-auto border-b border-line" aria-label="Title pages">
        <NavLink to={{ pathname: `/titles/${t.id}`, search }} end className={tab}>
          Overview
        </NavLink>
        <NavLink to={{ pathname: `/titles/${t.id}/reviews`, search }} className={tab}>
          Reviews
        </NavLink>
        <NavLink to={{ pathname: `/titles/${t.id}/analysis`, search }} className={tab}>
          Themes setup
        </NavLink>
      </nav>

      {!onAnalysis && <FilterBar titleId={t.id} appId={appId} />}
      <Outlet context={{ title: t, appId, filters: { ...filters, app: appId }, search } satisfies TitleContext} />
    </div>
  );
}

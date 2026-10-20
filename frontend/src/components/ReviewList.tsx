import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { api } from "../api/client";
import { filterQuery, type PageFilters } from "../lib/filters";
import { ReviewCard } from "./analysis/ReviewCard";
import { Button } from "./ui";

export const PAGE_SIZE = 20;

/** A page of reviews for the current filters. The page number lives in the URL. */
export function ReviewList({
  titleId,
  filters,
  query,
  focusTheme,
  empty = "No reviews match.",
}: {
  titleId: number;
  filters: PageFilters;
  query: { q?: string; theme?: string; sentiment?: string; overall?: string; sort?: string };
  focusTheme?: string;
  empty?: string;
}) {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const list = useQuery({
    queryKey: ["reviews", titleId, filterQuery(filters), query, page],
    queryFn: () => api.reviews(titleId, filters, { ...query, page, page_size: PAGE_SIZE }),
    placeholderData: keepPreviousData,
  });

  const goTo = (n: number) => {
    const next = new URLSearchParams(params);
    if (n > 1) next.set("page", String(n));
    else next.delete("page");
    setParams(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (list.isPending) return <p className="text-sm text-muted">Loading reviews...</p>;
  if (list.isError) return <p className="text-sm text-negative-ink">Could not load reviews: {list.error.message}</p>;
  const { total, reviews } = list.data;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const first = (page - 1) * PAGE_SIZE + 1;

  return (
    <div className={list.isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
      <p className="mb-3 text-xs text-muted" aria-live="polite">
        {total === 0 ? empty : `Showing ${first.toLocaleString()} to ${(first + reviews.length - 1).toLocaleString()} of ${total.toLocaleString()} reviews`}
      </p>
      <div className="space-y-3">
        {reviews.map((r) => (
          <ReviewCard key={r.id} review={r} focusTheme={focusTheme} />
        ))}
      </div>
      {pages > 1 && (
        <nav className="mt-4 flex items-center justify-between gap-3" aria-label="Pages">
          <Button onClick={() => goTo(page - 1)} disabled={page <= 1}>
            Previous
          </Button>
          <span className="text-sm text-muted">
            Page {page} of {pages}
          </span>
          <Button onClick={() => goTo(page + 1)} disabled={page >= pages}>
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}

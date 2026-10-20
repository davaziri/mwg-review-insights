import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import { Button, Card } from "../ui";
import { ReviewCard } from "./ReviewCard";

export function SpotCheck({ titleId, appId }: { titleId: number; appId: number }) {
  const [round, setRound] = useState(0);
  const sample = useQuery({
    queryKey: ["spot-check", titleId, appId, round],
    queryFn: () => api.taggedReviews(titleId, { app_id: appId, random: 20 }),
    enabled: round > 0,
    staleTime: Infinity,
  });

  return (
    <Card
      title="Spot check"
      actions={
        <Button onClick={() => setRound(round + 1)} disabled={sample.isFetching}>
          {round === 0 ? "Show 20 random tagged reviews" : "Show 20 different reviews"}
        </Button>
      }
    >
      <p className="text-sm text-slate-600">
        Read each review and check you agree with its overall impression, themes and sentiment. Highlighted text is copied exactly from the
        review and is what the app quotes; hover a highlight to see its theme. Bold outlined text is the quote behind the overall
        impression.
      </p>
      {sample.isError && <p className="mt-3 text-sm text-red-700">{sample.error.message}</p>}
      {sample.data && (
        <div className="mt-4 space-y-3">
          <p className="text-xs text-slate-500">
            {sample.data.reviews.length} of {sample.data.total.toLocaleString()} analyzed reviews, picked at random.
          </p>
          {sample.data.reviews.map((r) => (
            <ReviewCard key={r.id} review={r} />
          ))}
        </div>
      )}
    </Card>
  );
}

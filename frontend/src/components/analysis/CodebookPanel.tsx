import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { Codebook, Theme, ThemeDraft } from "../../api/types";
import { dateTime } from "../../lib/format";
import { Badge, Button, Card, inputClass } from "../ui";

const STATUS = { draft: { label: "Draft", tone: "amber" }, approved: { label: "Approved", tone: "green" }, superseded: { label: "Superseded", tone: "slate" } } as const;

type Working = ThemeDraft & { uid: number; originalKey?: string };

let uidCounter = 0;
const toWorking = (t: Theme): Working => ({
  uid: ++uidCounter,
  originalKey: t.key,
  key: t.key,
  name: t.name,
  definition: t.definition,
  include_notes: t.include_notes,
  exclude_notes: t.exclude_notes,
  example_review_ids: t.example_review_ids,
  derived_from: [],
});

export function CodebookPanel({ titleId, codebookId, approvedId }: { titleId: number; codebookId: number; approvedId: number | null }) {
  const queryClient = useQueryClient();
  const codebook = useQuery({ queryKey: ["codebook", codebookId], queryFn: () => api.codebook(codebookId) });
  const [editing, setEditing] = useState<Working[] | null>(null);

  const approve = useMutation({
    mutationFn: () => api.approveCodebook(codebookId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["analysis", titleId] }),
  });

  if (!codebook.data) return <Card title="Codebook">{codebook.isError ? codebook.error.message : "Loading..."}</Card>;
  const cb = codebook.data;
  const status = STATUS[cb.status];

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Codebook v{cb.version} <Badge tone={status.tone}>{status.label}</Badge>
        </span>
      }
      actions={
        !editing && (
          <>
            <Button onClick={() => setEditing((cb.themes ?? []).map(toWorking))}>Edit themes</Button>
            {cb.status === "draft" && (
              <Button variant="primary" onClick={() => approve.mutate()} disabled={approve.isPending}>
                Approve v{cb.version}
              </Button>
            )}
          </>
        )
      }
    >
      <p className="mb-3 text-xs text-muted">
        {cb.created_by}, {dateTime(cb.created_at)}
        {cb.note && <>. {cb.note}</>}
        {cb.status === "draft" && approvedId && approvedId !== cb.id && <>. Tagging still uses the approved version until you approve this one.</>}
      </p>
      {cb.needs_review_reason && (
        <div className="mb-3 rounded-md border border-mixed-line bg-mixed-soft px-3 py-2 text-sm text-mixed-ink">{cb.needs_review_reason}</div>
      )}
      {cb.status === "draft" && !editing && (
        <div className="mb-3 rounded-md border border-line bg-subtle px-3 py-2 text-sm text-ink-2">
          Review these themes before approving: rename, merge, split, add or delete them with Edit themes. Saving edits creates a new version.
        </div>
      )}
      {approve.isError && <p className="mb-3 text-sm text-negative-ink">{approve.error.message}</p>}

      {editing ? (
        <Editor
          codebook={cb}
          themes={editing}
          setThemes={setEditing}
          onDone={(saved) => {
            setEditing(null);
            if (saved) queryClient.invalidateQueries({ queryKey: ["analysis", titleId] });
          }}
        />
      ) : (
        <ol className="space-y-3">
          {(cb.themes ?? []).map((t) => (
            <ThemeView key={t.id} theme={t} codebook={cb} />
          ))}
        </ol>
      )}
    </Card>
  );
}

function ThemeView({ theme, codebook }: { theme: Theme; codebook: Codebook }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-md border border-line p-3">
      <div className="flex items-baseline gap-2">
        <span className="font-semibold">{theme.name}</span>
        <span className="text-xs text-faint">{theme.key}</span>
        <button type="button" className="ml-auto text-xs text-link hover:underline" onClick={() => setOpen(!open)}>
          {open ? "Less" : "Details"}
        </button>
      </div>
      <p className="text-sm text-ink-2">{theme.definition}</p>
      {open && (
        <div className="mt-2 space-y-1 text-sm">
          {theme.include_notes && (
            <p>
              <span className="font-medium">Include:</span> {theme.include_notes}
            </p>
          )}
          {theme.exclude_notes && (
            <p>
              <span className="font-medium">Exclude:</span> {theme.exclude_notes}
            </p>
          )}
          {theme.example_review_ids.map((id) => {
            const ex = codebook.examples?.[id];
            return ex ? (
              <blockquote key={id} className="border-l-2 border-line pl-3 text-xs text-ink-2">
                {ex.excerpt}{" "}
                <a className="text-link hover:underline" href={ex.url} target="_blank" rel="noreferrer">
                  Review {id}
                </a>
              </blockquote>
            ) : null;
          })}
        </div>
      )}
    </li>
  );
}

function Editor({
  codebook,
  themes,
  setThemes,
  onDone,
}: {
  codebook: Codebook;
  themes: Working[];
  setThemes: (t: Working[]) => void;
  onDone: (saved: boolean) => void;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [note, setNote] = useState("");
  const original = new Map((codebook.themes ?? []).map((t) => [t.key, t]));

  const update = (uid: number, patch: Partial<Working>) => setThemes(themes.map((t) => (t.uid === uid ? { ...t, ...patch } : t)));
  const remove = (uid: number) => setThemes(themes.filter((t) => t.uid !== uid));
  const split = (t: Working) => {
    const i = themes.findIndex((x) => x.uid === t.uid);
    const from = t.originalKey ? [{ key: t.originalKey, op: "split" }] : [{ op: "new" }];
    const first = { ...t, derived_from: from };
    const second: Working = { ...t, uid: ++uidCounter, key: null, originalKey: undefined, name: `${t.name} (2)`, derived_from: from };
    setThemes([...themes.slice(0, i), first, second, ...themes.slice(i + 1)]);
  };
  const merge = () => {
    const picked = themes.filter((t) => selected.has(t.uid));
    if (picked.length < 2) return;
    const merged: Working = {
      uid: ++uidCounter,
      key: picked[0].key,
      name: picked[0].name,
      definition: picked[0].definition,
      include_notes: picked.map((t) => t.include_notes).filter(Boolean).join(" "),
      exclude_notes: picked.map((t) => t.exclude_notes).filter(Boolean).join(" "),
      example_review_ids: [...new Set(picked.flatMap((t) => t.example_review_ids))].slice(0, 4),
      derived_from: picked.map((t) => ({ key: t.originalKey ?? t.key ?? undefined, op: "merged" })),
    };
    const at = themes.findIndex((t) => t.uid === picked[0].uid);
    const rest = themes.filter((t) => !selected.has(t.uid));
    rest.splice(Math.min(at, rest.length), 0, merged);
    setThemes(rest);
    setSelected(new Set());
  };
  const add = () =>
    setThemes([
      ...themes,
      { uid: ++uidCounter, key: null, name: "", definition: "", include_notes: "", exclude_notes: "", example_review_ids: [], derived_from: [{ op: "new" }] },
    ]);

  const lineage = (t: Working) => {
    if (t.derived_from.length) return t.derived_from;
    const before = t.originalKey ? original.get(t.originalKey) : undefined;
    if (!before) return [{ op: "new" }];
    const changed = before.name !== t.name || before.definition !== t.definition || before.include_notes !== t.include_notes || before.exclude_notes !== t.exclude_notes;
    return [{ key: before.key, op: before.name !== t.name ? "renamed" : changed ? "edited" : "kept" }];
  };

  const save = useMutation({
    mutationFn: (approve: boolean) =>
      api.saveCodebook(codebook.title_id, {
        parent_id: codebook.id,
        note: note.trim() || "Edited by the team",
        approve,
        themes: themes.map((t) => {
          const { uid, originalKey, ...draft } = t;
          return { ...draft, derived_from: lineage(t) };
        }),
      }),
    onSuccess: () => onDone(true),
  });
  const invalid = themes.length === 0 || themes.some((t) => !t.name.trim() || !t.definition.trim());

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
        <Button onClick={merge} disabled={selected.size < 2}>
          Merge selected ({selected.size})
        </Button>
        <Button onClick={add}>Add theme</Button>
        <span className="text-xs text-muted">{themes.length} themes. Tick two or more to merge them.</span>
      </div>
      <ol className="space-y-3">
        {themes.map((t) => (
          <li key={t.uid} className="rounded-md border border-line p-3">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                aria-label={`Select ${t.name || "theme"}`}
                checked={selected.has(t.uid)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(t.uid);
                  else next.delete(t.uid);
                  setSelected(next);
                }}
              />
              <input className={`${inputClass} font-semibold`} placeholder="Theme name" value={t.name} onChange={(e) => update(t.uid, { name: e.target.value })} />
              <Button variant="ghost" onClick={() => split(t)}>
                Split
              </Button>
              <Button variant="danger" onClick={() => remove(t.uid)}>
                Delete
              </Button>
            </div>
            <textarea className={`${inputClass} mt-2`} rows={2} placeholder="One-sentence definition" value={t.definition} onChange={(e) => update(t.uid, { definition: e.target.value })} />
            <div className="mt-2 grid gap-2 md:grid-cols-2">
              <textarea className={inputClass} rows={2} placeholder="Include: what counts" value={t.include_notes} onChange={(e) => update(t.uid, { include_notes: e.target.value })} />
              <textarea className={inputClass} rows={2} placeholder="Exclude: what doesn't, and which theme to use instead" value={t.exclude_notes} onChange={(e) => update(t.uid, { exclude_notes: e.target.value })} />
            </div>
          </li>
        ))}
      </ol>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input className={`${inputClass} max-w-sm`} placeholder="What changed (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button variant="ghost" onClick={() => onDone(false)} disabled={save.isPending}>
          Cancel
        </Button>
        <Button onClick={() => save.mutate(false)} disabled={invalid || save.isPending}>
          Save as new draft
        </Button>
        <Button variant="primary" onClick={() => save.mutate(true)} disabled={invalid || save.isPending}>
          Save and approve
        </Button>
      </div>
      {invalid && <p className="mt-2 text-xs text-muted">Every theme needs a name and a definition.</p>}
      {save.isError && <p className="mt-2 text-sm text-negative-ink">{save.error.message}</p>}
    </div>
  );
}

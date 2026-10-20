import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { api } from "../api/client";
import type { Title, TitleStatus } from "../api/types";
import { STATUS_LABELS } from "../api/types";
import { Button, Dialog, Field, inputClass } from "./ui";

const toId = (value: string) => (value.trim() ? Number(value.trim()) : null);

/** Add a new title (title is null) or edit an existing one. */
export function TitleFormDialog({
  title,
  onClose,
  onSaved,
}: {
  title: Title | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [appId, setAppId] = useState("");
  const [name, setName] = useState(title?.name ?? "");
  const [status, setStatus] = useState<TitleStatus>(title?.status ?? "released");
  const [demoId, setDemoId] = useState(title?.demo_app_id ? String(title.demo_app_id) : "");
  const [notes, setNotes] = useState(title?.notes ?? "");

  const save = useMutation({
    mutationFn: () =>
      title
        ? api.updateTitle(title.id, { name: name.trim() || title.name, status, demo_app_id: toId(demoId), notes: notes || null })
        : api.createTitle({
            steam_app_id: Number(appId),
            status,
            demo_app_id: toId(demoId),
            name: name.trim() || null,
            notes: notes || null,
          }),
    onSuccess: onSaved,
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  const validAppId = title !== null || /^\d+$/.test(appId.trim());
  const validDemo = demoId.trim() === "" || /^\d+$/.test(demoId.trim());

  return (
    <Dialog title={title ? `Edit ${title.name}` : "Add a title"} onClose={onClose}>
      <form onSubmit={submit}>
        {!title && (
          <Field label="Steam App ID" hint="The number in the store URL: store.steampowered.com/app/3308200">
            <input className={inputClass} value={appId} onChange={(e) => setAppId(e.target.value)} inputMode="numeric" autoFocus required />
          </Field>
        )}
        <Field label="Name" hint={title ? undefined : "Optional. Filled in from Steam if left blank."}>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Status">
          <select className={inputClass} value={status} onChange={(e) => setStatus(e.target.value as TitleStatus)}>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Demo App ID" hint="Optional. Demo reviews are synced separately and never mixed into the main numbers.">
          <input className={inputClass} value={demoId} onChange={(e) => setDemoId(e.target.value)} inputMode="numeric" />
        </Field>
        <Field label="Notes">
          <input className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>

        {save.isError && <p className="mb-3 text-sm text-negative-ink">{save.error.message}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={save.isPending || !validAppId || !validDemo}>
            {save.isPending ? "Saving..." : title ? "Save" : "Add and sync"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

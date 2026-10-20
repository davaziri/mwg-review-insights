import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Person } from "../api/types";
import { useAuth } from "../auth";
import { Badge, Card, selectClass } from "../components/ui";
import { timeAgo } from "../lib/format";

/** Everyone who has signed in, and what they can do. Admins only. */
export function PeoplePage() {
  const { me, isAdmin } = useAuth();
  const queryClient = useQueryClient();
  const people = useQuery({ queryKey: ["people"], queryFn: api.people, enabled: isAdmin && me.mode === "google" });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Pick<Person, "role" | "active">> }) => api.updatePerson(id, body),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["people"] }),
  });

  if (!isAdmin) return <p className="text-sm text-muted">Only admins can manage people.</p>;
  return (
    <div>
      <h1 className="text-xl font-semibold">People</h1>
      <p className="mb-5 max-w-3xl text-sm text-muted">
        Anyone with a Google account on the company's domain can sign in, and starts as a viewer: they can browse and export. Admins can also
        sync, edit themes, run analyses and manage people. Turning someone off signs them out straight away.
      </p>
      {me.mode === "local" && (
        <Card>
          <p className="text-sm text-ink-2">Sign-in is off (AUTH_MODE=local), so there is no one to manage. Turn on Google sign-in to use this page.</p>
        </Card>
      )}
      {update.isError && <p className="mb-3 text-sm text-negative-ink">{update.error.message}</p>}
      {people.data && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[620px] text-left text-sm">
            <thead className="border-b border-line text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-3 py-2">Person</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">Access</th>
                <th className="px-3 py-2">Last signed in</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {people.data.map((p) => (
                <tr key={p.id} className={p.active ? "" : "opacity-60"}>
                  <td className="px-3 py-2">
                    <div className="font-medium">{p.name ?? p.email}</div>
                    <div className="text-xs text-muted">
                      {p.email}
                      {p.email === me.user?.email && " (you)"}
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      aria-label={`Role for ${p.email}`}
                      className={selectClass}
                      value={p.role}
                      disabled={update.isPending}
                      onChange={(e) => update.mutate({ id: p.id, body: { role: e.target.value as Person["role"] } })}
                    >
                      <option value="viewer">Viewer</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={p.active}
                        disabled={update.isPending}
                        onChange={(e) => update.mutate({ id: p.id, body: { active: e.target.checked } })}
                      />
                      {p.active ? <Badge tone="green">On</Badge> : <Badge>Off</Badge>}
                    </label>
                  </td>
                  <td className="px-3 py-2 text-muted">{timeAgo(p.last_login_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

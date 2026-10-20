import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, type ReactNode } from "react";

import { api, setSignedOutHandler } from "./api/client";
import type { Me } from "./api/types";
import { brand } from "./theme/brand";

interface AuthState {
  me: Me;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

/** Shows the app to signed-in people and the sign-in page to everyone else. */
export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 5 * 60_000 });

  useEffect(() => {
    setSignedOutHandler(() => queryClient.invalidateQueries({ queryKey: ["me"] }));
  }, [queryClient]);

  if (me.isPending) return <p className="p-6 text-sm text-muted">Loading...</p>;
  if (me.isError) return <p className="p-6 text-sm text-negative-ink">Could not reach the app: {me.error.message}</p>;
  if (!me.data.user) return <SignInPage me={me.data} />;
  return <AuthContext.Provider value={{ me: me.data, isAdmin: me.data.user.role === "admin" }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const state = useContext(AuthContext);
  if (!state) throw new Error("useAuth needs an AuthGate");
  return state;
}

/** Renders its children only for admins. */
export function AdminOnly({ children, otherwise = null }: { children: ReactNode; otherwise?: ReactNode }) {
  return <>{useAuth().isAdmin ? children : otherwise}</>;
}

function SignInPage({ me }: { me: Me }) {
  const error = new URLSearchParams(window.location.search).get("signin_error");
  const next = window.location.pathname + window.location.search.replace(/([?&])signin_error=[^&]*/, "$1").replace(/[?&]$/, "");
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-lg border border-line bg-surface p-6 text-center shadow-sm">
        <img src={brand.logoUrl} alt="" className="mx-auto h-12 w-12" />
        <h1 className="mt-3 text-lg font-semibold">{brand.appName}</h1>
        <p className="text-sm text-muted">{brand.companyName}</p>
        {error && <p className="mt-4 rounded-md bg-negative-soft px-3 py-2 text-left text-sm text-negative-ink">{error}</p>}
        {me.problem ? (
          <p className="mt-4 rounded-md bg-info-soft px-3 py-2 text-left text-sm text-info-ink">{me.problem} The README explains how to set it up.</p>
        ) : (
          <a
            href={`/api/auth/login?next=${encodeURIComponent(next || "/")}`}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-medium text-on-brand hover:bg-brand-hover"
          >
            Sign in with Google
          </a>
        )}
        <p className="mt-4 text-xs text-muted">Use your {brand.companyName} Google account.</p>
      </div>
    </div>
  );
}

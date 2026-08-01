import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { UserSummary } from "@healthos/api-types";

import { authenticatedFetch } from "@/lib/auth";
import type { QueryHookOptions } from "./client";

/**
 * The signed-in account. Every role workspace needs it — the patient surfaces
 * key their reads on `patient_id`, and the shell keys its navigation on
 * `account_type` — so it lives in the query cache rather than in each
 * component's own effect.
 */

export const sessionQueryKey = ["auth", "session"] as const;

/** GET /api/v1/auth/session */
export function fetchSession(signal?: AbortSignal): Promise<UserSummary> {
  return authenticatedFetch<UserSummary>("/api/v1/auth/session", { signal });
}

export function useSession(
  options: QueryHookOptions = {},
): UseQueryResult<UserSummary> {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ signal }) => fetchSession(signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime ?? 60_000,
  });
}

/**
 * The patient whose record the current session may read.
 *
 * Clinical routes are keyed by the patient's **user UUID**, not by the
 * 15-character display id on `UserSummary.patient_id`. Only a patient session
 * resolves to one; for every other role the id must come from a picked row, so
 * this stays empty and the calling hooks stay disabled.
 */
export function usePatientId(): { patientId: string; isPending: boolean } {
  const session = useSession();
  const user = session.data;
  return {
    patientId: user?.account_type === "patient" ? user.id : "",
    isPending: session.isPending,
  };
}

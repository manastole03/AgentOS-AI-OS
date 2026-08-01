"use client";

import { useMemo } from "react";
import { useAppointments } from "@/lib/api/scheduling";
import type { AppointmentResponse } from "@/lib/api/types";

/**
 * The clinician's panel.
 *
 * There is no patient-directory endpoint — and there should not be one, since a
 * clinician may only read the records they have a relationship with. The panel
 * is therefore derived from the role-scoped appointment list, which the API
 * already narrows to this clinician's own patients and which carries the
 * display name alongside the user id the clinical routes are keyed on.
 */

export interface RosterEntry {
  patientUserId: string;
  name: string;
  visitCount: number;
  /** Most recent past appointment, ISO-8601. */
  lastSeenAt: string | null;
  /** Soonest future appointment that has not been cancelled, ISO-8601. */
  nextVisitAt: string | null;
}

export interface PatientRoster {
  entries: RosterEntry[];
  byId: Map<string, RosterEntry>;
  isPending: boolean;
  error: unknown;
}

const INACTIVE_STATUSES = new Set(["cancelled", "no-show"]);

export function rosterFromAppointments(
  appointments: readonly AppointmentResponse[],
  now: number,
): RosterEntry[] {
  const byId = new Map<string, RosterEntry>();

  for (const appointment of appointments) {
    const id = appointment.patient_user_id;
    const startedAt = new Date(appointment.start_at).getTime();
    const isFuture = Number.isFinite(startedAt) && startedAt >= now;
    const counts = !INACTIVE_STATUSES.has(appointment.status);

    const existing = byId.get(id);
    const entry: RosterEntry = existing ?? {
      patientUserId: id,
      name: appointment.patient_name ?? "Unnamed patient",
      visitCount: 0,
      lastSeenAt: null,
      nextVisitAt: null,
    };

    entry.visitCount += 1;
    if (!isFuture) {
      if (!entry.lastSeenAt || appointment.start_at > entry.lastSeenAt) {
        entry.lastSeenAt = appointment.start_at;
      }
    } else if (counts) {
      if (!entry.nextVisitAt || appointment.start_at < entry.nextVisitAt) {
        entry.nextVisitAt = appointment.start_at;
      }
    }
    if (!existing) byId.set(id, entry);
  }

  return [...byId.values()].sort((a, b) => {
    if (a.nextVisitAt && b.nextVisitAt) {
      return a.nextVisitAt.localeCompare(b.nextVisitAt);
    }
    if (a.nextVisitAt) return -1;
    if (b.nextVisitAt) return 1;
    return (b.lastSeenAt ?? "").localeCompare(a.lastSeenAt ?? "");
  });
}

export function usePatientRoster(): PatientRoster {
  const appointments = useAppointments({ limit: 200 });

  const entries = useMemo(
    () => rosterFromAppointments(appointments.data?.items ?? [], Date.now()),
    [appointments.data],
  );

  const byId = useMemo(
    () => new Map(entries.map((entry) => [entry.patientUserId, entry])),
    [entries],
  );

  return {
    entries,
    byId,
    isPending: appointments.isPending,
    error: appointments.error,
  };
}

/** Stable ISO bounds for the local calendar day, computed once per mount. */
export function dayBounds(reference: Date = new Date()): {
  from: string;
  to: string;
} {
  const start = new Date(reference);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { from: start.toISOString(), to: end.toISOString() };
}

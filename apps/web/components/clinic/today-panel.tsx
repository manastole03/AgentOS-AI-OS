"use client";

import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@healthos/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@healthos/ui/card";
import { DataTable } from "@healthos/ui/data-table";
import { EmptyState } from "@healthos/ui/empty-state";
import { Section } from "@healthos/ui/section";
import { StatTile } from "@healthos/ui/stat-tile";
import { StatusBadge, statusTone } from "@healthos/ui/status-badge";
import { Textarea } from "@healthos/ui/textarea";
import {
  CalendarCheck,
  CircleCheck,
  FilePen,
  OctagonX,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { qk } from "@/lib/api/client";
import { formatDateTime, formatDecimal, formatTimeRange } from "@/lib/api/format";
import { useAcknowledgeResult, useCriticalResults } from "@/lib/api/labs";
import { fetchEncounterNotes } from "@/lib/api/operations";
import { useAppointments } from "@/lib/api/scheduling";
import type {
  AppointmentResponse,
  ClinicalNoteOut,
  CriticalResultOut,
  Page,
} from "@/lib/api/types";
import { Field, FormDialog } from "@/components/workspace/form-dialog";
import { Panel, StatRowSkeleton } from "@/components/workspace/workspace-state";
import { dayBounds } from "@/components/clinic/use-patient-roster";

/**
 * The list a clinician opens the day on: who is coming, who is next, and the
 * two things the record is still waiting for — an unsigned note and an
 * unacknowledged panic value.
 */

const CLOSED_STATUSES = new Set(["cancelled", "no-show", "fulfilled"]);

const scheduleColumns: ColumnDef<AppointmentResponse>[] = [
  {
    id: "when",
    header: "Time",
    cell: ({ row }) => (
      <span className="tabular">
        {formatTimeRange(row.original.start_at, row.original.end_at)}
      </span>
    ),
  },
  {
    accessorKey: "patient_name",
    header: "Patient",
    cell: ({ row }) => (
      <span className="font-medium">
        {row.original.patient_name ?? "Unnamed patient"}
      </span>
    ),
  },
  {
    accessorKey: "channel",
    header: "Channel",
    cell: ({ row }) =>
      row.original.channel === "telehealth" ? "Telehealth" : "In person",
  },
  {
    accessorKey: "reason",
    header: "Reason",
    cell: ({ row }) => row.original.reason ?? "Not stated",
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        tone={statusTone(row.original.status)}
        label={row.original.status.replace(/-/g, " ")}
        size="sm"
      />
    ),
  },
];

function CriticalResultRow({ result }: { result: CriticalResultOut }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const acknowledge = useAcknowledgeResult();

  const value =
    result.value_numeric ?? result.value_string ?? "No value recorded";
  const outstanding = Number(result.outstanding_hours);

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 py-3">
      <div className="min-w-0 space-y-1">
        <p className="font-medium">{result.test_display}</p>
        <p className="text-sm text-muted-foreground">
          <span className="font-mono tabular">{value}</span>
          {result.unit ? ` ${result.unit}` : null} · order{" "}
          <span className="font-mono text-xs tabular">
            {result.order_number ?? "unlinked"}
          </span>
        </p>
        <p className="text-xs text-muted-foreground">
          Resulted {formatDateTime(result.effective_at)}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge
          tone="critical"
          label={`${formatDecimal(outstanding, { digits: 1 })} h outstanding`}
          icon={OctagonX}
          size="sm"
        />
        <Button size="sm" onClick={() => setOpen(true)}>
          Acknowledge
        </Button>
      </div>

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Acknowledge critical result"
        description={`${result.test_display} — recording who saw this value and when closes the call-back loop.`}
        submitLabel="Acknowledge"
        isPending={acknowledge.isPending}
        onSubmit={() => {
          acknowledge.mutate(
            {
              resultId: result.id,
              body: { note: note.trim() || null },
            },
            {
              onSuccess: () => {
                setOpen(false);
                setNote("");
              },
            },
          );
        }}
      >
        <Field label="Action taken" hint="Optional, stored with your name.">
          {(id) => (
            <Textarea
              id={id}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              placeholder="Patient called, repeat sample requested…"
            />
          )}
        </Field>
      </FormDialog>
    </li>
  );
}

export function TodayPanel({
  onOpenPatient,
  onOpenDocumentation,
}: {
  onOpenPatient: (patientUserId: string) => void;
  onOpenDocumentation: (patientUserId: string) => void;
}) {
  const today = useMemo(() => dayBounds(), []);
  const appointments = useAppointments({
    from: today.from,
    to: today.to,
    limit: 100,
  });
  const critical = useCriticalResults({ limit: 50 });

  const todaysAppointments = useMemo(
    () =>
      [...(appointments.data?.items ?? [])].sort((a, b) =>
        a.start_at.localeCompare(b.start_at),
      ),
    [appointments.data],
  );

  const encounterIds = useMemo(
    () =>
      Array.from(
        new Set(
          todaysAppointments
            .map((appointment) => appointment.encounter_id)
            .filter((id): id is string => Boolean(id)),
        ),
      ),
    [todaysAppointments],
  );

  const noteQueries = useQueries({
    queries: encounterIds.map((encounterId) => ({
      queryKey: qk.operations.encounterNoteList(encounterId, { limit: 25 }),
      queryFn: ({ signal }: { signal: AbortSignal }): Promise<Page<ClinicalNoteOut>> =>
        fetchEncounterNotes(encounterId, { limit: 25 }, signal),
    })),
  });

  const unsignedNotes = noteQueries
    .flatMap((query) => query.data?.items ?? [])
    .filter((note) => note.status === "draft");
  const notesPending = noteQueries.some((query) => query.isPending);

  const nextAppointment = todaysAppointments.find(
    (appointment) =>
      !CLOSED_STATUSES.has(appointment.status) &&
      new Date(appointment.end_at).getTime() >= Date.now(),
  );
  const remaining = todaysAppointments.filter(
    (appointment) => !CLOSED_STATUSES.has(appointment.status),
  ).length;
  const criticalCount = critical.data?.items.length ?? 0;

  return (
    <div className="space-y-6">
      {appointments.isPending || critical.isPending ? (
        <StatRowSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Appointments today"
            value={todaysAppointments.length}
            icon={CalendarCheck}
          />
          <StatTile label="Still to see" value={remaining} icon={UserRound} />
          <StatTile
            label="Critical results outstanding"
            value={criticalCount}
            icon={OctagonX}
          />
          <StatTile
            label="Unsigned notes"
            value={notesPending ? "—" : unsignedNotes.length}
            icon={FilePen}
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <Section
          title="Next patient"
          description="The first appointment today that is still open."
        >
          <Panel
            isPending={appointments.isPending}
            error={appointments.error}
            errorTitle="The schedule could not be loaded"
            skeletonRows={3}
          >
            {nextAppointment ? (
              <div className="space-y-4">
                <div>
                  <p className="text-lg font-semibold">
                    {nextAppointment.patient_name ?? "Unnamed patient"}
                  </p>
                  <p className="text-sm tabular text-muted-foreground">
                    {formatTimeRange(
                      nextAppointment.start_at,
                      nextAppointment.end_at,
                    )}{" "}
                    ·{" "}
                    {nextAppointment.channel === "telehealth"
                      ? "Telehealth"
                      : "In person"}
                  </p>
                </div>
                <p className="text-sm">
                  {nextAppointment.reason ?? "No reason recorded."}
                </p>
                <StatusBadge
                  tone={statusTone(nextAppointment.status)}
                  label={nextAppointment.status.replace(/-/g, " ")}
                  size="sm"
                />
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      onOpenPatient(nextAppointment.patient_user_id)
                    }
                  >
                    Open record
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      onOpenDocumentation(nextAppointment.patient_user_id)
                    }
                  >
                    Document visit
                  </Button>
                </div>
              </div>
            ) : (
              <EmptyState
                icon={CircleCheck}
                size="sm"
                title="Nothing left today"
                description="Every appointment on today's list has been closed out."
              />
            )}
          </Panel>
        </Section>

        <Section
          title="Today's schedule"
          description="Everything booked with you in the local calendar day."
          flush
          contentClassName="px-6"
        >
          <Panel
            isPending={appointments.isPending}
            error={appointments.error}
            errorTitle="The schedule could not be loaded"
          >
            <DataTable
              columns={scheduleColumns}
              data={todaysAppointments}
              emptyMessage="No appointments today"
              caption="Today's appointments"
              pageSize={8}
              getRowId={(row) => row.id}
            />
          </Panel>
        </Section>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Unacknowledged critical results"
          description="Panic values stay on this list until a clinician records the call-back."
        >
          <Panel
            isPending={critical.isPending}
            error={critical.error}
            errorTitle="The critical queue could not be loaded"
          >
            {critical.data?.items.length ? (
              <ul className="divide-y">
                {critical.data.items.map((result) => (
                  <CriticalResultRow key={result.id} result={result} />
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={CircleCheck}
                size="sm"
                title="No outstanding critical results"
                description="Every panic value in your scope has been acknowledged."
              />
            )}
          </Panel>
        </Section>

        <Section
          title="Unsigned notes"
          description="Drafts on today's encounters. A note is not part of the record until it is signed."
        >
          <Panel
            isPending={appointments.isPending || notesPending}
            error={appointments.error}
            errorTitle="Draft notes could not be loaded"
          >
            {unsignedNotes.length ? (
              <ul className="divide-y">
                {unsignedNotes.map((note) => (
                  <li
                    key={note.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">{note.title}</p>
                      <p className="text-xs text-muted-foreground">
                        Drafted {formatDateTime(note.recorded_at)} ·{" "}
                        {note.note_type_code}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <StatusBadge tone="warning" label="Draft" size="sm" />
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => onOpenDocumentation(note.patient_user_id)}
                      >
                        Open
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState
                icon={Stethoscope}
                size="sm"
                title="Nothing left to sign"
                description="Every note on today's encounters carries a signature."
              />
            )}
          </Panel>
        </Section>
      </div>
    </div>
  );
}

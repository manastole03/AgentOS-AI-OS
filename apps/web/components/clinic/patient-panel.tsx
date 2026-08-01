"use client";

import { useMemo, useState } from "react";
import { Badge } from "@healthos/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@healthos/ui/card";
import { EmptyState } from "@healthos/ui/empty-state";
import { Input } from "@healthos/ui/input";
import { ScrollArea } from "@healthos/ui/scroll-area";
import { Section } from "@healthos/ui/section";
import { Separator } from "@healthos/ui/separator";
import { StatusBadge, statusTone } from "@healthos/ui/status-badge";
import { cn } from "@healthos/utils";
import {
  Activity,
  SearchX,
  ShieldAlert,
  Syringe,
  UserRoundSearch,
} from "lucide-react";
import { usePatientSummary } from "@/lib/api/clinical";
import { formatDate, formatDateTime } from "@/lib/api/format";
import type { AllergyOut, Criticality, PatientSummary } from "@/lib/api/types";
import { Panel } from "@/components/workspace/workspace-state";
import type { PatientRoster } from "@/components/clinic/use-patient-roster";

/**
 * The clinical header.
 *
 * `GET /clinical/patients/{id}/summary` is the one request this screen makes:
 * conditions, allergies, the latest value for every vital, and the
 * immunisation position all arrive together, so nothing on the header can be
 * half a round trip behind the rest of it.
 */

const CRITICALITY_ORDER: Criticality[] = ["high", "low", "unable-to-assess"];

const CRITICALITY_TONE = {
  high: "critical",
  low: "warning",
  "unable-to-assess": "neutral",
} as const;

const CRITICALITY_LABEL: Record<Criticality, string> = {
  high: "High criticality",
  low: "Low criticality",
  "unable-to-assess": "Criticality not assessed",
};

function groupByCriticality(
  allergies: readonly AllergyOut[],
): Array<[Criticality, AllergyOut[]]> {
  return CRITICALITY_ORDER.map(
    (criticality) =>
      [
        criticality,
        allergies.filter((allergy) => allergy.criticality === criticality),
      ] as [Criticality, AllergyOut[]],
  ).filter(([, items]) => items.length > 0);
}

function AllergyBanner({ record }: { record: PatientSummary }) {
  if (record.allergy_status.no_known_allergies) {
    return (
      <StatusBadge
        tone="success"
        label="No known allergies"
        size="sm"
      />
    );
  }
  const groups = groupByCriticality(record.active_allergies);
  if (!groups.length) {
    return (
      <StatusBadge
        tone="warning"
        label="Allergy list never reviewed"
        size="sm"
      />
    );
  }
  return (
    <div className="space-y-3">
      {groups.map(([criticality, allergies]) => (
        <div key={criticality} className="space-y-1.5">
          <StatusBadge
            tone={CRITICALITY_TONE[criticality]}
            label={CRITICALITY_LABEL[criticality]}
            size="sm"
          />
          <ul className="space-y-1 text-sm">
            {allergies.map((allergy) => (
              <li key={allergy.id}>
                <span className="font-medium">{allergy.substance_display}</span>
                {allergy.reactions.length ? (
                  <span className="text-muted-foreground">
                    {" — "}
                    {allergy.reactions
                      .map((reaction) => reaction.manifestation_display)
                      .join(", ")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ClinicalHeader({ record }: { record: PatientSummary }) {
  const immunizations = record.immunizations;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="gap-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <CardTitle className="text-xl">{record.full_name}</CardTitle>
              <p className="mt-1 font-mono text-xs tabular text-muted-foreground">
                {record.patient_display_id}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {record.blood_type ? (
                <Badge variant="secondary">Blood {record.blood_type}</Badge>
              ) : null}
              {record.sex_at_birth ? (
                <Badge variant="outline" className="capitalize">
                  {record.sex_at_birth}
                </Badge>
              ) : null}
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 text-sm sm:grid-cols-3">
          <div>
            <p className="text-muted-foreground">Date of birth</p>
            <p className="tabular">
              {formatDate(record.date_of_birth, { fallback: "Not recorded" })}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Care team</p>
            <p>
              {record.care_team.length
                ? record.care_team
                    .map((member) => member.member_name ?? member.role_code)
                    .join(", ")
                : "Not assigned"}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Summary generated</p>
            <p className="tabular">{formatDateTime(record.generated_at)}</p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Allergies"
          description="Grouped by criticality — the highest risk reads first."
        >
          <AllergyBanner record={record} />
        </Section>

        <Section
          title="Active conditions"
          description="Problems currently on the list."
        >
          {record.active_conditions.length ? (
            <ul className="divide-y">
              {record.active_conditions.map((condition) => (
                <li
                  key={condition.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-2.5"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {condition.condition_display}
                    </p>
                    <p className="font-mono text-xs tabular text-muted-foreground">
                      {condition.condition_code}
                      {condition.onset_date
                        ? ` · onset ${formatDate(condition.onset_date, { style: "short" })}`
                        : null}
                    </p>
                  </div>
                  <StatusBadge
                    tone={statusTone(condition.clinical_status)}
                    label={condition.clinical_status.replace(/-/g, " ")}
                    size="sm"
                  />
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Activity}
              size="sm"
              title="No active conditions"
              description="Nothing is currently on this patient's problem list."
            />
          )}
        </Section>

        <Section
          title="Latest vitals"
          description="The most recent value recorded for each observation."
        >
          {record.latest_vitals.length ? (
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              {record.latest_vitals.map((vital) => (
                <div key={vital.id}>
                  <dt className="truncate text-xs text-muted-foreground">
                    {vital.observation_display}
                  </dt>
                  <dd className="font-mono text-lg font-semibold tabular">
                    {vital.value_numeric ?? vital.value_string ?? "—"}
                    {vital.unit ? (
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        {vital.unit}
                      </span>
                    ) : null}
                  </dd>
                  <p className="text-xs tabular text-muted-foreground">
                    {formatDate(vital.effective_at, { style: "short" })}
                  </p>
                </div>
              ))}
            </dl>
          ) : (
            <EmptyState
              icon={Activity}
              size="sm"
              title="No vitals recorded"
              description="Nothing has been measured for this patient yet."
            />
          )}
        </Section>

        <Section
          title="Immunisation status"
          description="Where this patient sits against their schedule."
        >
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <dt className="text-xs text-muted-foreground">Completed</dt>
                <dd className="font-mono text-lg font-semibold tabular">
                  {immunizations.completed}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Not done</dt>
                <dd className="font-mono text-lg font-semibold tabular">
                  {immunizations.not_done}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Overdue</dt>
                <dd className="font-mono text-lg font-semibold tabular">
                  {immunizations.overdue}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Upcoming</dt>
                <dd className="font-mono text-lg font-semibold tabular">
                  {immunizations.upcoming}
                </dd>
              </div>
            </dl>
            <Separator />
            <div className="flex flex-wrap items-center gap-3">
              {immunizations.overdue > 0 ? (
                <StatusBadge
                  tone="serious"
                  label={`${immunizations.overdue} dose${immunizations.overdue === 1 ? "" : "s"} overdue`}
                  icon={ShieldAlert}
                  size="sm"
                />
              ) : (
                <StatusBadge
                  tone="success"
                  label="Schedule up to date"
                  icon={Syringe}
                  size="sm"
                />
              )}
              <p className="text-sm text-muted-foreground">
                Next due{" "}
                <span className="tabular">
                  {formatDate(immunizations.next_due_at, {
                    fallback: "not scheduled",
                  })}
                </span>
              </p>
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}

export function PatientPanel({
  roster,
  selectedPatientId,
  onSelectPatient,
}: {
  roster: PatientRoster;
  selectedPatientId: string;
  onSelectPatient: (patientUserId: string) => void;
}) {
  const [query, setQuery] = useState("");
  const summary = usePatientSummary(selectedPatientId, {
    enabled: Boolean(selectedPatientId),
  });

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return roster.entries;
    return roster.entries.filter((entry) =>
      entry.name.toLowerCase().includes(needle),
    );
  }, [query, roster.entries]);

  return (
    <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <Section
        title="Your panel"
        description={`${roster.entries.length} patient${roster.entries.length === 1 ? "" : "s"} with a booked visit.`}
        contentClassName="space-y-3"
      >
        <Panel
          isPending={roster.isPending}
          error={roster.error}
          errorTitle="Your panel could not be loaded"
          skeletonRows={6}
        >
          <>
            <Input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search patients…"
              aria-label="Search patients"
            />
            {matches.length ? (
              <ScrollArea className="h-[28rem]" viewportClassName="pr-3">
                <ul className="space-y-1">
                  {matches.map((entry) => {
                    const active = entry.patientUserId === selectedPatientId;
                    return (
                      <li key={entry.patientUserId}>
                        <button
                          type="button"
                          onClick={() => onSelectPatient(entry.patientUserId)}
                          aria-current={active ? "true" : undefined}
                          className={cn(
                            "w-full rounded-md px-3 py-2 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                            active
                              ? "bg-accent text-accent-foreground"
                              : "hover:bg-muted",
                          )}
                        >
                          <span className="block truncate text-sm font-medium">
                            {entry.name}
                          </span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {entry.nextVisitAt
                              ? `Next ${formatDate(entry.nextVisitAt, { style: "short" })}`
                              : `Last seen ${formatDate(entry.lastSeenAt, { style: "short", fallback: "—" })}`}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </ScrollArea>
            ) : (
              <EmptyState
                icon={query ? SearchX : UserRoundSearch}
                size="sm"
                title={query ? "No patient matches" : "No patients yet"}
                description={
                  query
                    ? `Nothing on your panel matches “${query}”.`
                    : "Patients appear here once an appointment is booked with you."
                }
              />
            )}
          </>
        </Panel>
      </Section>

      <div>
        {selectedPatientId ? (
          <Panel
            isPending={summary.isPending}
            error={summary.error}
            errorTitle="The patient summary could not be loaded"
            skeletonRows={10}
          >
            {summary.data ? <ClinicalHeader record={summary.data} /> : null}
          </Panel>
        ) : (
          <EmptyState
            icon={UserRoundSearch}
            title="Choose a patient"
            description="Selecting a patient loads their conditions, allergies, latest vitals and immunisation position in one request."
          />
        )}
      </div>
    </div>
  );
}

"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { DataTable } from "@healthos/ui/data-table";
import { EmptyState } from "@healthos/ui/empty-state";
import { PageHeader } from "@healthos/ui/page-header";
import { Section } from "@healthos/ui/section";
import { StatTile } from "@healthos/ui/stat-tile";
import { StatusBadge, statusTone } from "@healthos/ui/status-badge";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@healthos/ui/tabs";
import { Activity, HeartPulse, ShieldQuestion, Syringe } from "lucide-react";
import {
  useAllergies,
  useConditions,
  useImmunizations,
  usePatientSummary,
  useVitals,
} from "@/lib/api/clinical";
import { usePatientId } from "@/lib/api/session";
import { formatDate } from "@/lib/api/format";
import type {
  AllergyOut,
  ConditionOut,
  ImmunizationOut,
} from "@/lib/api/types";
import { VitalsTrend } from "@/components/health/vitals-trend";
import { Panel, StatRowSkeleton } from "@/components/workspace/workspace-state";

/**
 * The patient's longitudinal record: what is currently true (summary tiles),
 * how a measure is moving (one chart, one measure), and the underlying lists.
 */

const criticalityTone = {
  high: "critical",
  low: "warning",
  "unable-to-assess": "neutral",
} as const;

const conditionColumns: ColumnDef<ConditionOut>[] = [
  {
    accessorKey: "condition_display",
    header: "Condition",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.condition_display}</span>
    ),
  },
  {
    accessorKey: "clinical_status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        tone={statusTone(row.original.clinical_status)}
        label={row.original.clinical_status.replace(/-/g, " ")}
        size="sm"
      />
    ),
  },
  {
    accessorKey: "severity_display",
    header: "Severity",
    cell: ({ row }) => row.original.severity_display ?? "Not recorded",
  },
  {
    accessorKey: "onset_date",
    header: "Onset",
    cell: ({ row }) =>
      formatDate(row.original.onset_date, { fallback: "Unknown" }),
    meta: { numeric: true },
  },
  {
    accessorKey: "condition_code",
    header: "Code",
    cell: ({ row }) => (
      <span className="font-mono text-xs tabular">
        {row.original.condition_code}
      </span>
    ),
  },
];

const allergyColumns: ColumnDef<AllergyOut>[] = [
  {
    accessorKey: "substance_display",
    header: "Substance",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.substance_display}</span>
    ),
  },
  {
    accessorKey: "criticality",
    header: "Criticality",
    cell: ({ row }) => (
      <StatusBadge
        tone={criticalityTone[row.original.criticality]}
        label={row.original.criticality.replace(/-/g, " ")}
        size="sm"
      />
    ),
  },
  {
    accessorKey: "category",
    header: "Category",
  },
  {
    id: "reactions",
    header: "Reactions",
    cell: ({ row }) =>
      row.original.reactions.length
        ? row.original.reactions
            .map((reaction) => reaction.manifestation_display)
            .join(", ")
        : "None recorded",
  },
  {
    accessorKey: "verification_status",
    header: "Verification",
  },
];

const immunizationColumns: ColumnDef<ImmunizationOut>[] = [
  {
    accessorKey: "vaccine_display",
    header: "Vaccine",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.vaccine_display}</span>
    ),
  },
  {
    accessorKey: "administered_date",
    header: "Administered",
    cell: ({ row }) => formatDate(row.original.administered_date),
    meta: { numeric: true },
  },
  {
    id: "dose",
    header: "Dose",
    cell: ({ row }) => {
      const { series_dose_number, series_doses_expected } = row.original;
      if (series_dose_number === null) return "—";
      return series_doses_expected
        ? `${series_dose_number} of ${series_doses_expected}`
        : String(series_dose_number);
    },
    meta: { numeric: true },
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
  {
    accessorKey: "next_due_at",
    header: "Next due",
    cell: ({ row }) =>
      formatDate(row.original.next_due_at, { fallback: "Not scheduled" }),
    meta: { numeric: true },
  },
];

export function HealthWorkspace() {
  const { patientId, isPending: sessionPending } = usePatientId();
  const enabled = Boolean(patientId);

  const summary = usePatientSummary(patientId);
  const vitals = useVitals(patientId, { limit: 200 }, { enabled });
  const allergies = useAllergies(patientId, { limit: 100 }, { enabled });
  const conditions = useConditions(patientId, { limit: 100 }, { enabled });
  const immunizations = useImmunizations(patientId, { limit: 100 }, { enabled });

  const vitalRows = useMemo(() => vitals.data?.items ?? [], [vitals.data]);

  if (!sessionPending && !patientId) {
    return (
      <EmptyState
        icon={HeartPulse}
        title="No patient record on this account"
        description="The health record is keyed to a patient session. Open a patient from the clinical workspace instead."
      />
    );
  }

  const record = summary.data;
  const immunizationSummary = record?.immunizations;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Health record"
        description={
          record
            ? `${record.full_name} · Health ID ${record.patient_display_id}`
            : "Conditions, allergies, immunizations, and vital trends."
        }
      />

      {summary.isPending ? (
        <StatRowSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Active conditions"
            value={record?.active_conditions.length ?? 0}
            icon={Activity}
          />
          <StatTile
            label="Active allergies"
            value={record?.allergy_status.active_allergy_count ?? 0}
            icon={ShieldQuestion}
          />
          <StatTile
            label="Immunizations completed"
            value={immunizationSummary?.completed ?? 0}
            icon={Syringe}
          />
          <StatTile
            label="Doses overdue"
            value={immunizationSummary?.overdue ?? 0}
            icon={Syringe}
          />
        </div>
      )}

      <Section
        title="Vital trend"
        description="One measure at a time — weight and heart rate never share an axis."
      >
        <Panel
          isPending={vitals.isPending}
          error={vitals.error}
          errorTitle="Vitals could not be loaded"
          skeletonRows={6}
        >
          <VitalsTrend vitals={vitalRows} />
        </Panel>
      </Section>

      <Tabs defaultValue="conditions">
        <TabsList>
          <TabsTrigger value="conditions">Conditions</TabsTrigger>
          <TabsTrigger value="allergies">Allergies</TabsTrigger>
          <TabsTrigger value="immunizations">Immunizations</TabsTrigger>
        </TabsList>

        <TabsContent value="conditions">
          <Panel
            isPending={conditions.isPending}
            error={conditions.error}
            errorTitle="Conditions could not be loaded"
          >
            <DataTable
              columns={conditionColumns}
              data={conditions.data?.items ?? []}
              searchKey="condition_display"
              searchPlaceholder="Search conditions…"
              emptyMessage="No conditions recorded"
              caption="Recorded conditions"
              getRowId={(row) => row.id}
            />
          </Panel>
        </TabsContent>

        <TabsContent value="allergies">
          <Panel
            isPending={allergies.isPending}
            error={allergies.error}
            errorTitle="Allergies could not be loaded"
          >
            <DataTable
              columns={allergyColumns}
              data={allergies.data?.items ?? []}
              searchKey="substance_display"
              searchPlaceholder="Search allergies…"
              emptyMessage="No allergies recorded"
              caption="Recorded allergies"
              getRowId={(row) => row.id}
            />
          </Panel>
        </TabsContent>

        <TabsContent value="immunizations">
          <Panel
            isPending={immunizations.isPending}
            error={immunizations.error}
            errorTitle="Immunizations could not be loaded"
          >
            <DataTable
              columns={immunizationColumns}
              data={immunizations.data?.items ?? []}
              searchKey="vaccine_display"
              searchPlaceholder="Search vaccines…"
              emptyMessage="No immunizations recorded"
              caption="Immunization history"
              getRowId={(row) => row.id}
            />
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}

"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import {
  CHART_BAR_PROPS,
  CHART_GRID_PROPS,
  CHART_X_AXIS_PROPS,
  CHART_Y_AXIS_PROPS,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  chartColorVar,
  type ChartConfig,
} from "@healthos/ui/chart";
import { DataTable } from "@healthos/ui/data-table";
import { EmptyState } from "@healthos/ui/empty-state";
import { PageHeader } from "@healthos/ui/page-header";
import { Section } from "@healthos/ui/section";
import { StatTile } from "@healthos/ui/stat-tile";
import { StatusBadge, statusTone } from "@healthos/ui/status-badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@healthos/ui/tabs";
import {
  BellRing,
  CalendarDays,
  FlaskConical,
  HeartPulse,
  Pill,
} from "lucide-react";
import { useAppointments } from "@/lib/api/scheduling";
import { useLabOrders } from "@/lib/api/labs";
import { useAdherence, useMedications, useReminders } from "@/lib/api/medications";
import { usePatientId } from "@/lib/api/session";
import {
  formatDate,
  formatDateTime,
  formatPercent,
  formatTimeRange,
} from "@/lib/api/format";
import type {
  AppointmentResponse,
  LabOrderOut,
  MedicationStatementOut,
  ReminderOut,
} from "@/lib/api/types";
import { Panel, StatRowSkeleton } from "@/components/workspace/workspace-state";

/**
 * The patient's active care: what is booked, what has to be taken, and what the
 * lab still owes them.
 */

const appointmentColumns: ColumnDef<AppointmentResponse>[] = [
  {
    id: "when",
    header: "When",
    cell: ({ row }) => (
      <div>
        <p className="font-medium">{formatDate(row.original.start_at)}</p>
        <p className="text-xs text-muted-foreground tabular">
          {formatTimeRange(row.original.start_at, row.original.end_at)}
        </p>
      </div>
    ),
  },
  {
    accessorKey: "provider_name",
    header: "Provider",
    cell: ({ row }) => row.original.provider_name ?? "Assigned at check-in",
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

const medicationColumns: ColumnDef<MedicationStatementOut>[] = [
  {
    accessorKey: "medication_display",
    header: "Medication",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.medication_display}</span>
    ),
  },
  {
    accessorKey: "sig_text",
    header: "Directions",
    cell: ({ row }) => row.original.sig_text ?? "As directed",
  },
  {
    accessorKey: "effective_start_at",
    header: "Started",
    cell: ({ row }) =>
      formatDate(row.original.effective_start_at, { fallback: "Unknown" }),
    meta: { numeric: true },
  },
  {
    accessorKey: "effective_end_at",
    header: "Ends",
    cell: ({ row }) =>
      formatDate(row.original.effective_end_at, { fallback: "Ongoing" }),
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
];

const labOrderColumns: ColumnDef<LabOrderOut>[] = [
  {
    accessorKey: "order_number",
    header: "Order",
    cell: ({ row }) => (
      <span className="font-mono text-xs tabular">
        {row.original.order_number}
      </span>
    ),
  },
  {
    accessorKey: "requested_at",
    header: "Requested",
    cell: ({ row }) => formatDate(row.original.requested_at),
    meta: { numeric: true },
  },
  {
    accessorKey: "test_count",
    header: "Tests",
    meta: { numeric: true },
  },
  {
    accessorKey: "priority",
    header: "Priority",
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        tone={statusTone(row.original.status)}
        label={row.original.status.replace(/_/g, " ")}
        size="sm"
      />
    ),
  },
];

function ReminderList({ reminders }: { reminders: ReminderOut[] }) {
  if (!reminders.length) {
    return (
      <EmptyState
        icon={BellRing}
        size="sm"
        title="Nothing due"
        description="No medication reminders are scheduled in this window."
      />
    );
  }
  return (
    <ul className="divide-y">
      {reminders.map((reminder) => (
        <li
          key={reminder.id}
          className="flex flex-wrap items-center justify-between gap-3 py-3"
        >
          <div className="min-w-0">
            <p className="truncate text-sm font-medium">
              {reminder.medication_display}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {reminder.dose_quantity} {reminder.dose_unit} ·{" "}
              {reminder.sig_text}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm tabular text-muted-foreground">
              {formatDateTime(reminder.scheduled_at)}
            </span>
            <StatusBadge
              tone={statusTone(reminder.status)}
              label={reminder.status}
              size="sm"
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

const adherenceConfig: ChartConfig = {
  rate: { label: "Doses taken" },
};

export function CareWorkspace() {
  const { patientId, isPending: sessionPending } = usePatientId();
  const enabled = Boolean(patientId);

  const appointments = useAppointments({ limit: 50 });
  const medications = useMedications(patientId, { limit: 50 }, { enabled });
  const reminders = useReminders(
    patientId,
    { window: "upcoming", limit: 10 },
    { enabled },
  );
  const adherence = useAdherence(patientId, { days: 30 }, { enabled });
  const labOrders = useLabOrders({ limit: 50 });

  const upcoming = useMemo(() => {
    const now = Date.now();
    return (appointments.data?.items ?? []).filter(
      (item) =>
        new Date(item.start_at).getTime() >= now &&
        item.status !== "cancelled" &&
        item.status !== "no-show",
    );
  }, [appointments.data]);

  const adherenceRows = useMemo(
    () =>
      (adherence.data?.items ?? [])
        .map((item) => ({
          medication: item.medication_display,
          rate: Number(item.adherence_rate) * 100,
        }))
        .filter((item) => Number.isFinite(item.rate))
        .slice(0, 8),
    [adherence.data],
  );

  if (!sessionPending && !patientId) {
    return (
      <EmptyState
        icon={HeartPulse}
        title="No patient record on this account"
        description="Care planning is keyed to a patient session."
      />
    );
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Care & medications"
        description="Appointments, medication courses, reminders, and lab orders."
      />

      {appointments.isPending || adherence.isPending ? (
        <StatRowSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Upcoming appointments"
            value={upcoming.length}
            icon={CalendarDays}
          />
          <StatTile
            label="Active medications"
            value={
              (medications.data?.items ?? []).filter(
                (item) => item.status === "active",
              ).length
            }
            icon={Pill}
          />
          <StatTile
            label="30-day adherence"
            value={formatPercent(adherence.data?.adherence_rate, {
              fallback: "—",
            })}
            icon={HeartPulse}
          />
          <StatTile
            label="Open lab orders"
            value={
              (labOrders.data?.items ?? []).filter(
                (item) => item.status !== "completed",
              ).length
            }
            icon={FlaskConical}
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Next reminders"
          description="Scheduled doses in the coming window."
        >
          <Panel
            isPending={reminders.isPending}
            error={reminders.error}
            errorTitle="Reminders could not be loaded"
          >
            <ReminderList reminders={reminders.data?.items ?? []} />
          </Panel>
        </Section>

        <Section
          title="Adherence by medication"
          description="Share of expected doses taken over the last 30 days."
        >
          <Panel
            isPending={adherence.isPending}
            error={adherence.error}
            errorTitle="Adherence could not be loaded"
          >
            {adherenceRows.length ? (
              <ChartContainer
                config={adherenceConfig}
                className="h-64 w-full"
                aria-label="Adherence rate by medication over the last 30 days"
              >
                <ResponsiveContainer>
                  <BarChart
                    data={adherenceRows}
                    margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
                  >
                    <CartesianGrid {...CHART_GRID_PROPS} />
                    <XAxis
                      {...CHART_X_AXIS_PROPS}
                      dataKey="medication"
                      tickFormatter={(value: string) =>
                        value.length > 14 ? `${value.slice(0, 13)}…` : value
                      }
                    />
                    <YAxis
                      {...CHART_Y_AXIS_PROPS}
                      domain={[0, 100]}
                      tickFormatter={(value: number) => `${value}%`}
                    />
                    <ChartTooltip
                      content={
                        <ChartTooltipContent
                          formatter={(value) =>
                            `${Number(value).toFixed(0)}% of doses`
                          }
                        />
                      }
                    />
                    <Bar
                      {...CHART_BAR_PROPS}
                      dataKey="rate"
                      name="rate"
                      fill={chartColorVar("rate")}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </ChartContainer>
            ) : (
              <EmptyState
                icon={Pill}
                size="sm"
                title="No adherence data yet"
                description="Adherence appears once a scheduled course has run."
              />
            )}
          </Panel>
        </Section>
      </div>

      <Tabs defaultValue="appointments">
        <TabsList>
          <TabsTrigger value="appointments">Appointments</TabsTrigger>
          <TabsTrigger value="medications">Medications</TabsTrigger>
          <TabsTrigger value="labs">Lab orders</TabsTrigger>
        </TabsList>

        <TabsContent value="appointments">
          <Panel
            isPending={appointments.isPending}
            error={appointments.error}
            errorTitle="Appointments could not be loaded"
          >
            <DataTable
              columns={appointmentColumns}
              data={appointments.data?.items ?? []}
              emptyMessage="No appointments booked"
              caption="Appointments"
              getRowId={(row) => row.id}
            />
          </Panel>
        </TabsContent>

        <TabsContent value="medications">
          <Panel
            isPending={medications.isPending}
            error={medications.error}
            errorTitle="Medications could not be loaded"
          >
            <DataTable
              columns={medicationColumns}
              data={medications.data?.items ?? []}
              searchKey="medication_display"
              searchPlaceholder="Search medications…"
              emptyMessage="No medications recorded"
              caption="Medication courses"
              getRowId={(row) => row.id}
            />
          </Panel>
        </TabsContent>

        <TabsContent value="labs">
          <Panel
            isPending={labOrders.isPending}
            error={labOrders.error}
            errorTitle="Lab orders could not be loaded"
          >
            <DataTable
              columns={labOrderColumns}
              data={labOrders.data?.items ?? []}
              searchKey="order_number"
              searchPlaceholder="Search by order number…"
              emptyMessage="No lab orders placed"
              caption="Lab orders"
              getRowId={(row) => row.id}
            />
          </Panel>
        </TabsContent>
      </Tabs>
    </div>
  );
}

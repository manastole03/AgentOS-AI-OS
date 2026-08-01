"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@healthos/ui/button";
import { DataTable } from "@healthos/ui/data-table";
import { Input } from "@healthos/ui/input";
import { Section } from "@healthos/ui/section";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@healthos/ui/select";
import { StatTile } from "@healthos/ui/stat-tile";
import { StatusBadge } from "@healthos/ui/status-badge";
import { Switch } from "@healthos/ui/switch";
import { CalendarPlus, CalendarRange, Clock } from "lucide-react";
import { formatDate, formatDateTime } from "@/lib/api/format";
import {
  useCreateProviderSchedule,
  useGenerateSlots,
  useProviderAvailability,
  useProviderSchedules,
} from "@/lib/api/scheduling";
import { useSession } from "@/lib/api/session";
import type { EncounterChannel, ProviderScheduleResponse } from "@/lib/api/types";
import {
  Field,
  FieldGrid,
  FormDialog,
} from "@/components/workspace/form-dialog";
import { Panel, StatRowSkeleton } from "@/components/workspace/workspace-state";

/**
 * Availability management.
 *
 * A schedule template is a weekly rule; publishing turns it into the concrete
 * slots patients can actually book. The two are separate on purpose — editing
 * the rule never silently moves an appointment somebody already holds.
 */

const DAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
] as const;

function localTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

interface TemplateForm {
  providerUserId: string;
  dayOfWeek: string;
  startTime: string;
  endTime: string;
  slotMinutes: string;
  timezone: string;
  channel: EncounterChannel;
  validFrom: string;
  validTo: string;
  isActive: boolean;
}

function emptyTemplateForm(providerUserId: string): TemplateForm {
  return {
    providerUserId,
    dayOfWeek: "0",
    startTime: "09:00",
    endTime: "17:00",
    slotMinutes: "30",
    timezone: localTimezone(),
    channel: "in_person",
    validFrom: "",
    validTo: "",
    isActive: true,
  };
}

function TemplateComposer({
  providerUserId,
  open,
  onOpenChange,
}: {
  providerUserId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [form, setForm] = useState<TemplateForm>(() =>
    emptyTemplateForm(providerUserId),
  );
  const create = useCreateProviderSchedule();

  const patch = (next: Partial<TemplateForm>) =>
    setForm((current) => ({ ...current, ...next }));
  const provider = form.providerUserId || providerUserId;

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setForm(emptyTemplateForm(providerUserId));
      }}
      title="New availability template"
      description="A weekly rule. Nothing is bookable until the template is published into slots."
      submitLabel="Save template"
      isPending={create.isPending}
      blockedReason={
        !provider
          ? "A provider user id is required."
          : !form.validFrom
            ? "Choose the date the template starts applying."
            : form.startTime >= form.endTime
              ? "The end time must be after the start time."
              : null
      }
      onSubmit={() => {
        create.mutate(
          {
            provider_user_id: provider,
            day_of_week: Number(form.dayOfWeek),
            start_time: `${form.startTime}:00`,
            end_time: `${form.endTime}:00`,
            slot_minutes: Number(form.slotMinutes) || 30,
            timezone: form.timezone,
            channel: form.channel,
            valid_from: form.validFrom,
            valid_to: form.validTo || null,
            is_active: form.isActive,
          },
          {
            onSuccess: () => {
              onOpenChange(false);
              setForm(emptyTemplateForm(providerUserId));
            },
          },
        );
      }}
    >
      <Field
        label="Provider user id"
        required
        hint="Defaults to your own account."
      >
        {(id) => (
          <Input
            id={id}
            value={provider}
            onChange={(event) => patch({ providerUserId: event.target.value })}
          />
        )}
      </Field>

      <FieldGrid>
        <Field label="Day of week" required>
          {(id) => (
            <Select
              value={form.dayOfWeek}
              onValueChange={(value) => patch({ dayOfWeek: value })}
            >
              <SelectTrigger id={id}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DAY_NAMES.map((day, index) => (
                  <SelectItem key={day} value={String(index)}>
                    {day}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Channel">
          {(id) => (
            <Select
              value={form.channel}
              onValueChange={(value) =>
                patch({ channel: value as EncounterChannel })
              }
            >
              <SelectTrigger id={id}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="in_person">In person</SelectItem>
                <SelectItem value="telehealth">Telehealth</SelectItem>
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Start time" required>
          {(id) => (
            <Input
              id={id}
              type="time"
              value={form.startTime}
              onChange={(event) => patch({ startTime: event.target.value })}
            />
          )}
        </Field>
        <Field label="End time" required>
          {(id) => (
            <Input
              id={id}
              type="time"
              value={form.endTime}
              onChange={(event) => patch({ endTime: event.target.value })}
            />
          )}
        </Field>
        <Field label="Slot length (minutes)">
          {(id) => (
            <Input
              id={id}
              type="number"
              min={5}
              step={5}
              value={form.slotMinutes}
              onChange={(event) => patch({ slotMinutes: event.target.value })}
            />
          )}
        </Field>
        <Field label="Timezone" required>
          {(id) => (
            <Input
              id={id}
              value={form.timezone}
              onChange={(event) => patch({ timezone: event.target.value })}
            />
          )}
        </Field>
        <Field label="Valid from" required>
          {(id) => (
            <Input
              id={id}
              type="date"
              value={form.validFrom}
              onChange={(event) => patch({ validFrom: event.target.value })}
            />
          )}
        </Field>
        <Field label="Valid to" hint="Leave blank for an open-ended rule.">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={form.validTo}
              onChange={(event) => patch({ validTo: event.target.value })}
            />
          )}
        </Field>
      </FieldGrid>

      <label className="flex items-center gap-3 text-sm">
        <Switch
          checked={form.isActive}
          onCheckedChange={(checked) => patch({ isActive: checked })}
          aria-label="Template active"
        />
        Active
      </label>
    </FormDialog>
  );
}

function PublishSlots({ schedule }: { schedule: ProviderScheduleResponse }) {
  const [open, setOpen] = useState(false);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [capacity, setCapacity] = useState("1");
  const [priceCents, setPriceCents] = useState("");
  const [currency, setCurrency] = useState("USD");
  const generate = useGenerateSlots();

  return (
    <>
      <Button size="xs" variant="outline" onClick={() => setOpen(true)}>
        Publish slots
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Publish bookable slots"
        description={`${DAY_NAMES[schedule.day_of_week] ?? "Day"} ${schedule.start_time}–${schedule.end_time}. Slots that already exist are skipped, never duplicated.`}
        submitLabel="Publish"
        isPending={generate.isPending}
        blockedReason={
          !fromDate || !toDate
            ? "Choose the date range to publish."
            : toDate < fromDate
              ? "The end date must not precede the start date."
              : null
        }
        onSubmit={() => {
          generate.mutate(
            {
              scheduleId: schedule.id,
              body: {
                from_date: fromDate,
                to_date: toDate,
                capacity: Number(capacity) || 1,
                price_cents: priceCents.trim()
                  ? Math.round(Number(priceCents) * 100)
                  : null,
                currency: priceCents.trim() ? currency : null,
              },
            },
            { onSuccess: () => setOpen(false) },
          );
        }}
      >
        <FieldGrid>
          <Field label="From" required>
            {(id) => (
              <Input
                id={id}
                type="date"
                value={fromDate}
                onChange={(event) => setFromDate(event.target.value)}
              />
            )}
          </Field>
          <Field label="To" required>
            {(id) => (
              <Input
                id={id}
                type="date"
                value={toDate}
                onChange={(event) => setToDate(event.target.value)}
              />
            )}
          </Field>
          <Field label="Capacity per slot">
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
              />
            )}
          </Field>
          <Field
            label="Consultation fee"
            hint="In major units. Leave blank for no charge at booking."
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                step="0.01"
                value={priceCents}
                onChange={(event) => setPriceCents(event.target.value)}
              />
            )}
          </Field>
          <Field label="Currency">
            {(id) => (
              <Input
                id={id}
                value={currency}
                maxLength={3}
                onChange={(event) =>
                  setCurrency(event.target.value.toUpperCase())
                }
              />
            )}
          </Field>
        </FieldGrid>
      </FormDialog>
    </>
  );
}

const scheduleColumns: ColumnDef<ProviderScheduleResponse>[] = [
  {
    accessorKey: "day_of_week",
    header: "Day",
    cell: ({ row }) => DAY_NAMES[row.original.day_of_week] ?? "—",
  },
  {
    id: "hours",
    header: "Hours",
    cell: ({ row }) => (
      <span className="tabular">
        {row.original.start_time}–{row.original.end_time}
      </span>
    ),
  },
  {
    accessorKey: "slot_minutes",
    header: "Slot",
    cell: ({ row }) => `${row.original.slot_minutes} min`,
    meta: { numeric: true },
  },
  {
    accessorKey: "channel",
    header: "Channel",
    cell: ({ row }) =>
      row.original.channel === "telehealth" ? "Telehealth" : "In person",
  },
  {
    accessorKey: "timezone",
    header: "Timezone",
  },
  {
    id: "validity",
    header: "Valid",
    cell: ({ row }) =>
      `${formatDate(row.original.valid_from, { style: "short" })} – ${formatDate(
        row.original.valid_to,
        { style: "short", fallback: "open" },
      )}`,
    meta: { numeric: true },
  },
  {
    accessorKey: "is_active",
    header: "State",
    cell: ({ row }) => (
      <StatusBadge
        tone={row.original.is_active ? "success" : "neutral"}
        label={row.original.is_active ? "Active" : "Paused"}
        size="sm"
      />
    ),
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => <PublishSlots schedule={row.original} />,
    meta: { align: "right" },
  },
];

export function SchedulePanel() {
  const session = useSession();
  const providerUserId = session.data?.id ?? "";
  const [composerOpen, setComposerOpen] = useState(false);

  const schedules = useProviderSchedules(
    { provider_user_id: providerUserId || null, limit: 50 },
    { enabled: Boolean(providerUserId) },
  );

  const horizon = useMemo(() => {
    const from = new Date();
    const to = new Date(from);
    to.setDate(to.getDate() + 28);
    return { from: from.toISOString(), to: to.toISOString() };
  }, []);

  const availability = useProviderAvailability({
    from: horizon.from,
    to: horizon.to,
    limit: 200,
  });

  const slots = availability.data?.items ?? [];
  const openSlots = slots.filter((slot) => slot.remaining > 0);
  const nextSlot = openSlots
    .map((slot) => slot.start_at)
    .sort((a, b) => a.localeCompare(b))[0];

  return (
    <div className="space-y-6">
      {schedules.isPending || availability.isPending ? (
        <StatRowSkeleton tiles={3} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatTile
            label="Active templates"
            value={
              (schedules.data?.items ?? []).filter((item) => item.is_active)
                .length
            }
            icon={CalendarRange}
          />
          <StatTile
            label="Bookable slots (28 days)"
            value={openSlots.length}
            icon={CalendarPlus}
          />
          <StatTile
            label="Next opening"
            value={
              nextSlot
                ? formatDateTime(nextSlot, { style: "short" })
                : "None published"
            }
            icon={Clock}
          />
        </div>
      )}

      <Section
        title="Availability templates"
        description="The weekly rules behind patient booking. Publishing a template creates the slots patients see."
        action={
          <Button
            size="sm"
            onClick={() => setComposerOpen(true)}
            disabled={!providerUserId}
          >
            New template
          </Button>
        }
        flush
        contentClassName="px-6"
      >
        <Panel
          isPending={session.isPending || schedules.isPending}
          error={schedules.error ?? session.error}
          errorTitle="Schedule templates could not be loaded"
        >
          <DataTable
            columns={scheduleColumns}
            data={schedules.data?.items ?? []}
            emptyMessage="No availability templates yet"
            caption="Provider schedule templates"
            getRowId={(row) => row.id}
          />
        </Panel>
      </Section>

      {providerUserId ? (
        <TemplateComposer
          providerUserId={providerUserId}
          open={composerOpen}
          onOpenChange={setComposerOpen}
        />
      ) : null}
    </div>
  );
}

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
import { StatusBadge, statusTone } from "@healthos/ui/status-badge";
import { Switch } from "@healthos/ui/switch";
import { Textarea } from "@healthos/ui/textarea";
import { Flame } from "lucide-react";
import { formatDate, formatDateTime } from "@/lib/api/format";
import {
  useChangeReferralStatus,
  useCreateReferral,
  useReferrals,
} from "@/lib/api/operations";
import type { ReferralOut, ReferralStatus } from "@/lib/api/types";
import {
  Field,
  FieldGrid,
  FormDialog,
} from "@/components/workspace/form-dialog";
import { Panel } from "@/components/workspace/workspace-state";
import { PatientPicker } from "@/components/clinic/patient-picker";
import type { PatientRoster } from "@/components/clinic/use-patient-roster";

/**
 * Referrals out and in. A referral is raised as a draft or sent immediately,
 * then walks a state machine the API owns — this table is the worklist for
 * both directions.
 */

type Urgency = "routine" | "urgent" | "emergent";

const REFERRAL_STATUSES: ReferralStatus[] = [
  "draft",
  "sent",
  "accepted",
  "declined",
  "scheduled",
  "completed",
  "expired",
];

const URGENCIES: Urgency[] = ["routine", "urgent", "emergent"];

const URGENCY_TONE = {
  routine: "neutral",
  urgent: "warning",
  emergent: "critical",
} as const;

interface ReferralForm {
  specialtyCode: string;
  reason: string;
  urgency: Urgency;
  receivingProviderUserId: string;
  expiresAt: string;
  send: boolean;
}

const emptyReferralForm = (): ReferralForm => ({
  specialtyCode: "",
  reason: "",
  urgency: "routine",
  receivingProviderUserId: "",
  expiresAt: "",
  send: true,
});

function ReferralComposer({
  roster,
  patientUserId,
  onSelectPatient,
  open,
  onOpenChange,
}: {
  roster: PatientRoster;
  patientUserId: string;
  onSelectPatient: (patientUserId: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [form, setForm] = useState<ReferralForm>(emptyReferralForm);
  const create = useCreateReferral();

  const patch = (next: Partial<ReferralForm>) =>
    setForm((current) => ({ ...current, ...next }));

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setForm(emptyReferralForm());
      }}
      title="Raise a referral"
      description="Send it now or keep it as a draft until the receiving service is chosen."
      submitLabel={form.send ? "Send referral" : "Save draft"}
      isPending={create.isPending}
      blockedReason={
        !patientUserId
          ? "Choose the patient this referral is for."
          : !form.specialtyCode.trim() || !form.reason.trim()
            ? "A specialty code and a reason are required."
            : null
      }
      onSubmit={() => {
        create.mutate(
          {
            patient_user_id: patientUserId,
            specialty_code: form.specialtyCode.trim(),
            reason: form.reason.trim(),
            urgency: form.urgency,
            receiving_provider_user_id:
              form.receivingProviderUserId.trim() || null,
            expires_at: form.expiresAt
              ? new Date(form.expiresAt).toISOString()
              : null,
            send: form.send,
          },
          {
            onSuccess: () => {
              onOpenChange(false);
              setForm(emptyReferralForm());
            },
          },
        );
      }}
    >
      <Field label="Patient" required>
        {() => (
          <PatientPicker
            roster={roster}
            value={patientUserId}
            onChange={onSelectPatient}
          />
        )}
      </Field>

      <FieldGrid>
        <Field label="Specialty code" required hint="e.g. CARD, ORTHO, DERM.">
          {(id) => (
            <Input
              id={id}
              value={form.specialtyCode}
              maxLength={64}
              onChange={(event) => patch({ specialtyCode: event.target.value })}
            />
          )}
        </Field>
        <Field label="Urgency">
          {(id) => (
            <Select
              value={form.urgency}
              onValueChange={(value) => patch({ urgency: value as Urgency })}
            >
              <SelectTrigger id={id}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {URGENCIES.map((urgency) => (
                  <SelectItem key={urgency} value={urgency}>
                    <span className="capitalize">{urgency}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
      </FieldGrid>

      <Field label="Reason" required>
        {(id) => (
          <Textarea
            id={id}
            value={form.reason}
            onChange={(event) => patch({ reason: event.target.value })}
            placeholder="What the receiving service is being asked to do."
          />
        )}
      </Field>

      <FieldGrid>
        <Field
          label="Receiving provider user id"
          hint="Optional. Leave blank to route by specialty."
        >
          {(id) => (
            <Input
              id={id}
              value={form.receivingProviderUserId}
              onChange={(event) =>
                patch({ receivingProviderUserId: event.target.value })
              }
              placeholder="00000000-0000-0000-0000-000000000000"
            />
          )}
        </Field>
        <Field label="Expires">
          {(id) => (
            <Input
              id={id}
              type="date"
              value={form.expiresAt}
              onChange={(event) => patch({ expiresAt: event.target.value })}
            />
          )}
        </Field>
      </FieldGrid>

      <label className="flex items-center gap-3 text-sm">
        <Switch
          checked={form.send}
          onCheckedChange={(checked) => patch({ send: checked })}
          aria-label="Send immediately"
        />
        Send immediately instead of saving a draft
      </label>
    </FormDialog>
  );
}

function ReferralStatusAction({ referral }: { referral: ReferralOut }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<ReferralStatus>("accepted");
  const [reason, setReason] = useState("");
  const change = useChangeReferralStatus();

  return (
    <>
      <Button size="xs" variant="outline" onClick={() => setOpen(true)}>
        Advance
      </Button>
      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Advance the referral"
        description={`${referral.specialty_code} · currently ${referral.status}. The API rejects a transition the state machine does not allow.`}
        submitLabel="Save status"
        isPending={change.isPending}
        onSubmit={() => {
          change.mutate(
            {
              referralId: referral.id,
              body: { status, reason: reason.trim() || null },
            },
            {
              onSuccess: () => {
                setOpen(false);
                setReason("");
              },
            },
          );
        }}
      >
        <Field label="New status" required>
          {(id) => (
            <Select
              value={status}
              onValueChange={(value) => setStatus(value as ReferralStatus)}
            >
              <SelectTrigger id={id}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {REFERRAL_STATUSES.map((item) => (
                  <SelectItem key={item} value={item}>
                    <span className="capitalize">{item}</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Reason" hint="Recorded as feedback on the referral.">
          {(id) => (
            <Textarea
              id={id}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          )}
        </Field>
      </FormDialog>
    </>
  );
}

const referralColumns: ColumnDef<ReferralOut>[] = [
  {
    accessorKey: "specialty_code",
    header: "Specialty",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.specialty_code}</span>
    ),
  },
  {
    accessorKey: "reason",
    header: "Reason",
    cell: ({ row }) => (
      <span className="line-clamp-2">{row.original.reason}</span>
    ),
  },
  {
    accessorKey: "urgency",
    header: "Urgency",
    cell: ({ row }) => {
      const urgency = row.original.urgency as Urgency;
      return (
        <StatusBadge
          tone={URGENCY_TONE[urgency] ?? "neutral"}
          label={urgency}
          icon={urgency === "emergent" ? Flame : undefined}
          size="sm"
          className="capitalize"
        />
      );
    },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        tone={statusTone(row.original.status)}
        label={row.original.status}
        size="sm"
        className="capitalize"
      />
    ),
  },
  {
    accessorKey: "created_at",
    header: "Raised",
    cell: ({ row }) => formatDateTime(row.original.created_at),
    meta: { numeric: true },
  },
  {
    accessorKey: "expires_at",
    header: "Expires",
    cell: ({ row }) =>
      formatDate(row.original.expires_at, { fallback: "No expiry" }),
    meta: { numeric: true },
  },
  {
    id: "actions",
    header: "",
    cell: ({ row }) => <ReferralStatusAction referral={row.original} />,
    meta: { align: "right" },
  },
];

export function ReferralsPanel({
  roster,
  selectedPatientId,
  onSelectPatient,
}: {
  roster: PatientRoster;
  selectedPatientId: string;
  onSelectPatient: (patientUserId: string) => void;
}) {
  const [status, setStatus] = useState<ReferralStatus | "all">("all");
  const [direction, setDirection] = useState<"all" | "incoming" | "outgoing">(
    "all",
  );
  const [composerOpen, setComposerOpen] = useState(false);

  const query = useMemo(
    () => ({
      limit: 100,
      status: status === "all" ? null : status,
      direction: direction === "all" ? null : direction,
    }),
    [status, direction],
  );
  const referrals = useReferrals(query);

  return (
    <Section
      title="Referrals"
      description="Everything you have sent and everything sent to you, with the state machine that governs both."
      action={
        <Button size="sm" onClick={() => setComposerOpen(true)}>
          New referral
        </Button>
      }
      flush
      contentClassName="space-y-4 px-6"
    >
      <div className="flex flex-col gap-3 sm:flex-row">
        <Select
          value={direction}
          onValueChange={(value) =>
            setDirection(value as "all" | "incoming" | "outgoing")
          }
        >
          <SelectTrigger className="w-full sm:w-48" aria-label="Direction">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Both directions</SelectItem>
            <SelectItem value="outgoing">Outgoing</SelectItem>
            <SelectItem value="incoming">Incoming</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={status}
          onValueChange={(value) => setStatus(value as ReferralStatus | "all")}
        >
          <SelectTrigger className="w-full sm:w-48" aria-label="Status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any status</SelectItem>
            {REFERRAL_STATUSES.map((item) => (
              <SelectItem key={item} value={item}>
                <span className="capitalize">{item}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Panel
        isPending={referrals.isPending}
        error={referrals.error}
        errorTitle="Referrals could not be loaded"
      >
        <DataTable
          columns={referralColumns}
          data={referrals.data?.items ?? []}
          searchKey="specialty_code"
          searchPlaceholder="Search by specialty…"
          emptyMessage="No referrals match these filters"
          caption="Referral worklist"
          getRowId={(row) => row.id}
        />
      </Panel>

      <ReferralComposer
        roster={roster}
        patientUserId={selectedPatientId}
        onSelectPatient={onSelectPatient}
        open={composerOpen}
        onOpenChange={setComposerOpen}
      />
    </Section>
  );
}

"use client";

import { useMemo, useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Button } from "@healthos/ui/button";
import { DataTable } from "@healthos/ui/data-table";
import { EmptyState } from "@healthos/ui/empty-state";
import { Input } from "@healthos/ui/input";
import { Section } from "@healthos/ui/section";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@healthos/ui/select";
import {
  StatusBadge,
  type StatusTone,
} from "@healthos/ui/status-badge";
import { Bot, UserRoundSearch } from "lucide-react";
import { formatDateTime, formatPercent } from "@/lib/api/format";
import { useCreateEncounterCode, useEncounterCodes } from "@/lib/api/operations";
import type {
  CodeType,
  EncounterCodeOut,
  ReviewStatus,
} from "@/lib/api/types";
import {
  Field,
  FieldGrid,
  FormDialog,
} from "@/components/workspace/form-dialog";
import { Panel } from "@/components/workspace/workspace-state";
import { EncounterPicker } from "@/components/clinic/encounter-picker";
import { PatientPicker } from "@/components/clinic/patient-picker";
import type { PatientRoster } from "@/components/clinic/use-patient-roster";

/**
 * Billing codes on an encounter.
 *
 * A code carries where it came from and how sure that source was. An
 * AI-extracted suggestion is worth nothing until a human accepts it, so the
 * review column is the point of this table, not an afterthought.
 */

const CODE_SYSTEM_BY_TYPE: Record<CodeType, string> = {
  diagnosis: "http://hl7.org/fhir/sid/icd-10-cm",
  procedure: "http://www.ama-assn.org/go/cpt",
  hcpcs: "https://www.cms.gov/Medicare/Coding/HCPCSReleaseCodeSets",
};

const CODE_TYPE_LABEL: Record<CodeType, string> = {
  diagnosis: "ICD-10-CM diagnosis",
  procedure: "CPT procedure",
  hcpcs: "HCPCS Level II",
};

const REVIEW_TONE: Record<ReviewStatus, StatusTone> = {
  pending: "warning",
  accepted: "success",
  rejected: "critical",
};

const REVIEW_LABEL: Record<ReviewStatus, string> = {
  pending: "Awaiting review",
  accepted: "Human accepted",
  rejected: "Human rejected",
};

const codeColumns: ColumnDef<EncounterCodeOut>[] = [
  {
    accessorKey: "billing_code",
    header: "Code",
    cell: ({ row }) => (
      <span className="font-mono text-xs tabular">
        {row.original.billing_code}
      </span>
    ),
  },
  {
    accessorKey: "billing_display",
    header: "Description",
    cell: ({ row }) => (
      <span className="font-medium">{row.original.billing_display}</span>
    ),
  },
  {
    accessorKey: "code_type",
    header: "Type",
    cell: ({ row }) => CODE_TYPE_LABEL[row.original.code_type],
  },
  {
    accessorKey: "rank",
    header: "Rank",
    meta: { numeric: true },
  },
  {
    accessorKey: "units",
    header: "Units",
    meta: { numeric: true },
  },
  {
    accessorKey: "source",
    header: "Source",
    cell: ({ row }) =>
      row.original.source === "ai-extracted" ? (
        <span className="inline-flex items-center gap-1.5">
          <Bot aria-hidden="true" className="size-3.5 text-muted-foreground" />
          AI extracted
        </span>
      ) : (
        row.original.source.replace(/-/g, " ")
      ),
  },
  {
    accessorKey: "confidence",
    header: "Confidence",
    cell: ({ row }) =>
      formatPercent(row.original.confidence, { fallback: "Not scored" }),
    meta: { numeric: true },
  },
  {
    accessorKey: "review_status",
    header: "Review",
    cell: ({ row }) => (
      <StatusBadge
        tone={REVIEW_TONE[row.original.review_status]}
        label={REVIEW_LABEL[row.original.review_status]}
        size="sm"
      />
    ),
  },
  {
    accessorKey: "reviewed_at",
    header: "Reviewed",
    cell: ({ row }) =>
      formatDateTime(row.original.reviewed_at, { fallback: "—" }),
    meta: { numeric: true },
  },
];

interface CodeForm {
  codeType: CodeType;
  codeSystem: string;
  code: string;
  display: string;
  rank: string;
  units: string;
  modifiers: string;
  confidence: string;
  reviewStatus: ReviewStatus;
}

const emptyCodeForm = (): CodeForm => ({
  codeType: "diagnosis",
  codeSystem: CODE_SYSTEM_BY_TYPE.diagnosis,
  code: "",
  display: "",
  rank: "",
  units: "1",
  modifiers: "",
  confidence: "",
  reviewStatus: "accepted",
});

function CodeComposer({
  encounterId,
  open,
  onOpenChange,
}: {
  encounterId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [form, setForm] = useState<CodeForm>(emptyCodeForm);
  const create = useCreateEncounterCode();

  const patch = (next: Partial<CodeForm>) =>
    setForm((current) => ({ ...current, ...next }));

  const confidenceValue = form.confidence.trim()
    ? Number(form.confidence) / 100
    : null;
  const confidenceInvalid =
    confidenceValue !== null &&
    (!Number.isFinite(confidenceValue) ||
      confidenceValue < 0 ||
      confidenceValue > 1);

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setForm(emptyCodeForm());
      }}
      title="Add a billing code"
      description="Coding an encounter records who coded it. Accepting an AI suggestion records you as the human reviewer."
      submitLabel="Add code"
      isPending={create.isPending}
      blockedReason={
        !form.code.trim() || !form.display.trim()
          ? "A code and a description are required."
          : confidenceInvalid
            ? "Confidence must be a percentage between 0 and 100."
            : null
      }
      onSubmit={() => {
        create.mutate(
          {
            encounterId,
            body: {
              billing_code_system: form.codeSystem.trim(),
              billing_code: form.code.trim(),
              billing_display: form.display.trim(),
              code_type: form.codeType,
              rank: form.rank.trim() ? Number(form.rank) : null,
              units: form.units.trim() ? Number(form.units) : 1,
              modifiers: form.modifiers
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
              confidence: confidenceValue,
              review_status: form.reviewStatus,
            },
          },
          {
            onSuccess: () => {
              onOpenChange(false);
              setForm(emptyCodeForm());
            },
          },
        );
      }}
    >
      <FieldGrid>
        <Field label="Code type" required>
          {(id) => (
            <Select
              value={form.codeType}
              onValueChange={(value) =>
                patch({
                  codeType: value as CodeType,
                  codeSystem: CODE_SYSTEM_BY_TYPE[value as CodeType],
                })
              }
            >
              <SelectTrigger id={id}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(CODE_TYPE_LABEL) as CodeType[]).map((type) => (
                  <SelectItem key={type} value={type}>
                    {CODE_TYPE_LABEL[type]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
        <Field label="Code" required hint="e.g. E11.9 or 99213.">
          {(id) => (
            <Input
              id={id}
              value={form.code}
              maxLength={64}
              onChange={(event) => patch({ code: event.target.value })}
            />
          )}
        </Field>
      </FieldGrid>

      <Field label="Description" required>
        {(id) => (
          <Input
            id={id}
            value={form.display}
            maxLength={255}
            onChange={(event) => patch({ display: event.target.value })}
            placeholder="Type 2 diabetes mellitus without complications"
          />
        )}
      </Field>

      <Field
        label="Code system"
        required
        hint="Pre-filled from the code type; override only for a non-standard system."
      >
        {(id) => (
          <Input
            id={id}
            value={form.codeSystem}
            maxLength={128}
            onChange={(event) => patch({ codeSystem: event.target.value })}
          />
        )}
      </Field>

      <FieldGrid>
        <Field label="Rank" hint="1 is the principal code.">
          {(id) => (
            <Input
              id={id}
              type="number"
              min={1}
              value={form.rank}
              onChange={(event) => patch({ rank: event.target.value })}
            />
          )}
        </Field>
        <Field label="Units">
          {(id) => (
            <Input
              id={id}
              type="number"
              min={1}
              value={form.units}
              onChange={(event) => patch({ units: event.target.value })}
            />
          )}
        </Field>
        <Field label="Modifiers" hint="Comma separated.">
          {(id) => (
            <Input
              id={id}
              value={form.modifiers}
              onChange={(event) => patch({ modifiers: event.target.value })}
              placeholder="25, 59"
            />
          )}
        </Field>
        <Field
          label="Confidence (%)"
          hint="Leave blank when a human chose the code outright."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              max={100}
              value={form.confidence}
              onChange={(event) => patch({ confidence: event.target.value })}
            />
          )}
        </Field>
      </FieldGrid>

      <Field
        label="Review status"
        hint="Anything not accepted stays on the coder's worklist."
      >
        {(id) => (
          <Select
            value={form.reviewStatus}
            onValueChange={(value) =>
              patch({ reviewStatus: value as ReviewStatus })
            }
          >
            <SelectTrigger id={id}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(REVIEW_LABEL) as ReviewStatus[]).map((status) => (
                <SelectItem key={status} value={status}>
                  {REVIEW_LABEL[status]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </Field>
    </FormDialog>
  );
}

export function CodingPanel({
  roster,
  selectedPatientId,
  onSelectPatient,
}: {
  roster: PatientRoster;
  selectedPatientId: string;
  onSelectPatient: (patientUserId: string) => void;
}) {
  const [encounterId, setEncounterId] = useState("");
  const [codeType, setCodeType] = useState<CodeType | "all">("all");
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus | "all">("all");
  const [composerOpen, setComposerOpen] = useState(false);

  const query = useMemo(
    () => ({
      limit: 100,
      code_type: codeType === "all" ? null : codeType,
      review_status: reviewStatus === "all" ? null : reviewStatus,
    }),
    [codeType, reviewStatus],
  );

  const codes = useEncounterCodes(encounterId, query, {
    enabled: Boolean(encounterId),
  });

  const awaitingReview = (codes.data?.items ?? []).filter(
    (code) => code.review_status === "pending",
  ).length;

  return (
    <div className="space-y-6">
      <Section
        title="Encounter"
        description="Codes attach to a visit, so pick the patient and the visit first."
        contentClassName="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center"
      >
        <PatientPicker
          roster={roster}
          value={selectedPatientId}
          onChange={onSelectPatient}
        />
        {selectedPatientId ? (
          <EncounterPicker
            patientUserId={selectedPatientId}
            value={encounterId}
            onChange={setEncounterId}
          />
        ) : null}
      </Section>

      {!selectedPatientId ? (
        <EmptyState
          icon={UserRoundSearch}
          title="Choose a patient"
          description="Coding is scoped to one patient's encounter at a time."
        />
      ) : !encounterId ? null : (
        <Section
          title="Encounter codes"
          description={
            awaitingReview > 0
              ? `${awaitingReview} code${awaitingReview === 1 ? "" : "s"} still need a human decision.`
              : "Every code on this encounter has been reviewed."
          }
          action={
            <Button size="sm" onClick={() => setComposerOpen(true)}>
              Add code
            </Button>
          }
          flush
          contentClassName="space-y-4 px-6"
        >
          <div className="flex flex-col gap-3 sm:flex-row">
            <Select
              value={codeType}
              onValueChange={(value) => setCodeType(value as CodeType | "all")}
            >
              <SelectTrigger className="w-full sm:w-56" aria-label="Code type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All code types</SelectItem>
                {(Object.keys(CODE_TYPE_LABEL) as CodeType[]).map((type) => (
                  <SelectItem key={type} value={type}>
                    {CODE_TYPE_LABEL[type]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={reviewStatus}
              onValueChange={(value) =>
                setReviewStatus(value as ReviewStatus | "all")
              }
            >
              <SelectTrigger
                className="w-full sm:w-56"
                aria-label="Review status"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any review status</SelectItem>
                {(Object.keys(REVIEW_LABEL) as ReviewStatus[]).map((status) => (
                  <SelectItem key={status} value={status}>
                    {REVIEW_LABEL[status]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Panel
            isPending={codes.isPending}
            error={codes.error}
            errorTitle="Encounter codes could not be loaded"
          >
            <DataTable
              columns={codeColumns}
              data={codes.data?.items ?? []}
              searchKey="billing_display"
              searchPlaceholder="Search descriptions…"
              emptyMessage="No codes on this encounter"
              caption="Encounter billing codes"
              getRowId={(row) => row.id}
            />
          </Panel>

          <CodeComposer
            encounterId={encounterId}
            open={composerOpen}
            onOpenChange={setComposerOpen}
          />
        </Section>
      )}
    </div>
  );
}

"use client";

import { useState } from "react";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import { Card, CardContent, CardHeader } from "@healthos/ui/card";
import { EmptyState } from "@healthos/ui/empty-state";
import { Input } from "@healthos/ui/input";
import { Section } from "@healthos/ui/section";
import { Separator } from "@healthos/ui/separator";
import { StatusBadge } from "@healthos/ui/status-badge";
import { Switch } from "@healthos/ui/switch";
import { Textarea } from "@healthos/ui/textarea";
import {
  FilePen,
  FileText,
  Lock,
  ShieldCheck,
  UserRoundSearch,
} from "lucide-react";
import { formatDateTime } from "@/lib/api/format";
import {
  useAddNoteAddendum,
  useCreateEncounterNote,
  useEncounterNotes,
  useSignNote,
} from "@/lib/api/operations";
import type { ClinicalNoteOut } from "@/lib/api/types";
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
 * Documentation, with the database's own rule made visible.
 *
 * `clinical_notes` carries a trigger that rejects every UPDATE and DELETE once
 * `signed_at` is set. A signed note therefore renders as a read-only record
 * with exactly one affordance — add an addendum — because that is the only
 * write the database will accept. An unsigned draft still offers a replacement
 * version, which is a new row that supersedes the old one rather than an edit.
 */

interface NoteDraftForm {
  title: string;
  noteTypeCode: string;
  content: string;
  amendmentReason: string;
}

const EMPTY_DRAFT: NoteDraftForm = {
  title: "",
  noteTypeCode: "",
  content: "",
  amendmentReason: "",
};

function NoteComposer({
  encounterId,
  supersedes,
  open,
  onOpenChange,
}: {
  encounterId: string;
  supersedes: ClinicalNoteOut | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [form, setForm] = useState<NoteDraftForm>(EMPTY_DRAFT);
  const create = useCreateEncounterNote();
  const replacing = supersedes !== null;

  const patch = (next: Partial<NoteDraftForm>) =>
    setForm((current) => ({ ...current, ...next }));

  const title = replacing ? form.title || supersedes.title : form.title;
  const noteTypeCode = replacing
    ? form.noteTypeCode || supersedes.note_type_code
    : form.noteTypeCode;

  return (
    <FormDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next) setForm(EMPTY_DRAFT);
      }}
      title={replacing ? "Replace draft" : "New draft note"}
      description={
        replacing
          ? "The current draft is superseded by a new version. Nothing is overwritten."
          : "Saved as a draft. It becomes part of the record only when you sign it."
      }
      submitLabel={replacing ? "Save replacement" : "Save draft"}
      isPending={create.isPending}
      blockedReason={
        !title.trim() || !noteTypeCode.trim() || !form.content.trim()
          ? "A title, a note type code and note content are all required."
          : null
      }
      onSubmit={() => {
        create.mutate(
          {
            encounterId,
            body: {
              title: title.trim(),
              note_type_code: noteTypeCode.trim(),
              content: form.content.trim(),
              content_format: "markdown",
              source: "practitioner",
              supersedes_id: supersedes?.id ?? null,
              amendment_reason: replacing
                ? form.amendmentReason.trim() || null
                : null,
            },
          },
          {
            onSuccess: () => {
              onOpenChange(false);
              setForm(EMPTY_DRAFT);
            },
          },
        );
      }}
    >
      <FieldGrid>
        <Field label="Title" required>
          {(id) => (
            <Input
              id={id}
              value={title}
              maxLength={255}
              onChange={(event) => patch({ title: event.target.value })}
              placeholder="Follow-up visit"
            />
          )}
        </Field>
        <Field
          label="Note type code"
          required
          hint="Short document type code, e.g. PN for a progress note."
        >
          {(id) => (
            <Input
              id={id}
              value={noteTypeCode}
              maxLength={16}
              onChange={(event) => patch({ noteTypeCode: event.target.value })}
              placeholder="PN"
            />
          )}
        </Field>
      </FieldGrid>
      <Field label="Note" required hint="Markdown is preserved as written.">
        {(id) => (
          <Textarea
            id={id}
            value={form.content}
            rows={10}
            className="min-h-48"
            onChange={(event) => patch({ content: event.target.value })}
            placeholder="Subjective, objective, assessment, plan…"
          />
        )}
      </Field>
      {replacing ? (
        <Field
          label="Reason for the replacement"
          hint="Stored on the new version so the change is explainable later."
        >
          {(id) => (
            <Input
              id={id}
              value={form.amendmentReason}
              maxLength={500}
              onChange={(event) =>
                patch({ amendmentReason: event.target.value })
              }
              placeholder="Corrected medication dose"
            />
          )}
        </Field>
      ) : null}
    </FormDialog>
  );
}

function SignedNoteRecord({ note }: { note: ClinicalNoteOut }) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-muted/40 p-4">
        <p className="whitespace-pre-wrap text-sm leading-relaxed">
          {note.content}
        </p>
      </div>
      <dl className="grid gap-3 text-xs sm:grid-cols-3">
        <div>
          <dt className="text-muted-foreground">Signed</dt>
          <dd className="tabular">{formatDateTime(note.signed_at)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Version</dt>
          <dd className="tabular">{note.version}</dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Signature</dt>
          <dd className="truncate font-mono tabular">
            {note.signature_hash ?? "—"}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function AddendumList({ note }: { note: ClinicalNoteOut }) {
  if (!note.addenda.length) return null;
  return (
    <div className="space-y-3">
      <Separator />
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Addenda
      </p>
      <ol className="space-y-3">
        {note.addenda.map((addendum) => (
          <li key={addendum.id} className="rounded-md border border-border p-3">
            <p className="text-xs tabular text-muted-foreground">
              #{addendum.sequence} · signed {formatDateTime(addendum.signed_at)}
            </p>
            <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
              {addendum.content}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function NoteCard({
  note,
  encounterId,
}: {
  note: ClinicalNoteOut;
  encounterId: string;
}) {
  const [signOpen, setSignOpen] = useState(false);
  const [addendumOpen, setAddendumOpen] = useState(false);
  const [replaceOpen, setReplaceOpen] = useState(false);
  const [cosigner, setCosigner] = useState("");
  const [addendum, setAddendum] = useState("");

  const sign = useSignNote();
  const addAddendum = useAddNoteAddendum();
  const locked = note.signed_at !== null;

  return (
    <Card>
      <CardHeader className="gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate font-semibold">{note.title}</p>
            <p className="text-xs text-muted-foreground">
              {note.note_type_code} · recorded{" "}
              <span className="tabular">
                {formatDateTime(note.recorded_at)}
              </span>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {note.superseded_at ? (
              <Badge variant="outline">Superseded</Badge>
            ) : null}
            <StatusBadge
              tone={locked ? "success" : "warning"}
              icon={locked ? Lock : FilePen}
              label={locked ? "Signed — read only" : "Draft"}
              size="sm"
            />
          </div>
        </div>
        {locked ? (
          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <ShieldCheck aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
            <span>
              The database rejects any change to a signed note. An addendum is
              the only write it will accept.
            </span>
          </p>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-4">
        {locked ? (
          <SignedNoteRecord note={note} />
        ) : (
          <div className="rounded-lg border border-dashed border-border p-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {note.content}
            </p>
          </div>
        )}

        <AddendumList note={note} />

        <div className="flex flex-wrap gap-2">
          {locked ? (
            <Button size="sm" onClick={() => setAddendumOpen(true)}>
              Add addendum
            </Button>
          ) : (
            <>
              <Button size="sm" onClick={() => setSignOpen(true)}>
                Sign note
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setReplaceOpen(true)}
              >
                Replace draft
              </Button>
            </>
          )}
        </div>
      </CardContent>

      <FormDialog
        open={signOpen}
        onOpenChange={setSignOpen}
        title="Sign this note"
        description="Signing writes a signature hash and locks the row. After this the note can only be amended with an addendum."
        submitLabel="Sign"
        isPending={sign.isPending}
        onSubmit={() => {
          sign.mutate(
            {
              noteId: note.id,
              body: { cosigner_user_id: cosigner.trim() || null },
            },
            {
              onSuccess: () => {
                setSignOpen(false);
                setCosigner("");
              },
            },
          );
        }}
      >
        <Field
          label="Cosigner user id"
          hint="Optional. The supervising clinician's HealthOS user UUID."
        >
          {(id) => (
            <Input
              id={id}
              value={cosigner}
              onChange={(event) => setCosigner(event.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
            />
          )}
        </Field>
      </FormDialog>

      <FormDialog
        open={addendumOpen}
        onOpenChange={setAddendumOpen}
        title="Add an addendum"
        description="The addendum is signed on submission and appended below the note. The original text is untouched."
        submitLabel="Sign addendum"
        isPending={addAddendum.isPending}
        blockedReason={!addendum.trim() ? "An addendum needs content." : null}
        onSubmit={() => {
          addAddendum.mutate(
            {
              noteId: note.id,
              encounterId,
              body: { content: addendum.trim() },
            },
            {
              onSuccess: () => {
                setAddendumOpen(false);
                setAddendum("");
              },
            },
          );
        }}
      >
        <Field label="Addendum" required>
          {(id) => (
            <Textarea
              id={id}
              value={addendum}
              rows={8}
              className="min-h-40"
              onChange={(event) => setAddendum(event.target.value)}
              placeholder="Correction, late result, or clarification…"
            />
          )}
        </Field>
      </FormDialog>

      <NoteComposer
        encounterId={encounterId}
        supersedes={note}
        open={replaceOpen}
        onOpenChange={setReplaceOpen}
      />
    </Card>
  );
}

export function DocumentationPanel({
  roster,
  selectedPatientId,
  onSelectPatient,
}: {
  roster: PatientRoster;
  selectedPatientId: string;
  onSelectPatient: (patientUserId: string) => void;
}) {
  const [encounterId, setEncounterId] = useState("");
  const [includeSuperseded, setIncludeSuperseded] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);

  const notes = useEncounterNotes(
    encounterId,
    { limit: 50, include_superseded: includeSuperseded },
    { enabled: Boolean(encounterId) },
  );

  return (
    <div className="space-y-6">
      <Section
        title="Encounter"
        description="Notes belong to a visit, so pick the patient and the visit first."
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
          description="Documentation is scoped to one patient's encounter at a time."
        />
      ) : !encounterId ? null : (
        <Section
          title="Notes"
          description="Drafts can be signed or replaced. Signed notes are read-only for good."
          action={
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <Switch
                  checked={includeSuperseded}
                  onCheckedChange={setIncludeSuperseded}
                  aria-label="Show superseded versions"
                />
                <span className="hidden sm:inline">Show superseded</span>
              </label>
              <Button size="sm" onClick={() => setComposerOpen(true)}>
                New draft
              </Button>
            </div>
          }
        >
          <Panel
            isPending={notes.isPending}
            error={notes.error}
            errorTitle="Notes could not be loaded"
            skeletonRows={5}
          >
            {notes.data?.items.length ? (
              <div className="space-y-4">
                {notes.data.items.map((note) => (
                  <NoteCard
                    key={note.id}
                    note={note}
                    encounterId={encounterId}
                  />
                ))}
              </div>
            ) : (
              <EmptyState
                icon={FileText}
                size="sm"
                title="No notes on this encounter"
                description="Start a draft — nothing enters the record until it is signed."
                action={
                  <Button size="sm" onClick={() => setComposerOpen(true)}>
                    New draft
                  </Button>
                }
              />
            )}
          </Panel>

          <NoteComposer
            encounterId={encounterId}
            supersedes={null}
            open={composerOpen}
            onOpenChange={setComposerOpen}
          />
        </Section>
      )}
    </div>
  );
}

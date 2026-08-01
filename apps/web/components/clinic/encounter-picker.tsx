"use client";

import { useEffect } from "react";
import { EmptyState } from "@healthos/ui/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@healthos/ui/select";
import { Skeleton } from "@healthos/ui/skeleton";
import { CalendarClock } from "lucide-react";
import { useEncounters } from "@/lib/api/clinical";
import { formatDate } from "@/lib/api/format";
import type { EncounterOut } from "@/lib/api/types";
import { PanelError } from "@/components/workspace/workspace-state";

const CLASS_LABELS: Record<EncounterOut["class_code"], string> = {
  AMB: "Ambulatory",
  IMP: "Inpatient",
  EMER: "Emergency",
  VR: "Virtual",
  HH: "Home health",
};

export function encounterLabel(encounter: EncounterOut): string {
  const when = formatDate(encounter.started_at, { style: "medium" });
  const reason = encounter.reason_text ? ` · ${encounter.reason_text}` : "";
  return `${when} · ${CLASS_LABELS[encounter.class_code]}${reason}`;
}

/**
 * Notes and billing codes hang off an encounter, never off a patient directly,
 * so both tabs need the same second choice. The most recent encounter is
 * selected for the caller as soon as the list arrives.
 */
export function EncounterPicker({
  patientUserId,
  value,
  onChange,
}: {
  patientUserId: string;
  value: string;
  onChange: (encounterId: string) => void;
}) {
  const encounters = useEncounters(
    patientUserId,
    { limit: 50 },
    { enabled: Boolean(patientUserId) },
  );
  const items = encounters.data?.items ?? [];
  const firstId = items[0]?.id ?? "";
  const isKnown = items.some((item) => item.id === value);

  useEffect(() => {
    if (!isKnown && firstId) onChange(firstId);
  }, [firstId, isKnown, onChange]);

  if (!patientUserId) return null;
  if (encounters.isPending) return <Skeleton className="h-10 w-full sm:w-96" />;
  if (encounters.error) {
    return (
      <PanelError
        error={encounters.error}
        title="Encounters could not be loaded"
      />
    );
  }
  if (!items.length) {
    return (
      <EmptyState
        icon={CalendarClock}
        size="sm"
        title="No encounters for this patient"
        description="Documentation and coding attach to a visit, so one has to be opened first."
      />
    );
  }

  return (
    <Select value={isKnown ? value : firstId} onValueChange={onChange}>
      <SelectTrigger className="w-full sm:w-96" aria-label="Encounter">
        <SelectValue placeholder="Choose an encounter" />
      </SelectTrigger>
      <SelectContent>
        {items.map((encounter) => (
          <SelectItem key={encounter.id} value={encounter.id}>
            {encounterLabel(encounter)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

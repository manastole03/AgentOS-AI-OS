"use client";

import { EmptyState } from "@healthos/ui/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@healthos/ui/select";
import { Skeleton } from "@healthos/ui/skeleton";
import { UsersRound } from "lucide-react";
import { PanelError } from "@/components/workspace/workspace-state";
import type { PatientRoster } from "@/components/clinic/use-patient-roster";

/**
 * One patient chooser, shared by every tab that is keyed on a patient. Keeping
 * the choice in the workspace means moving between documentation, coding and
 * the record never re-asks who is in the room.
 */
export function PatientPicker({
  roster,
  value,
  onChange,
  label = "Patient",
}: {
  roster: PatientRoster;
  value: string;
  onChange: (patientUserId: string) => void;
  label?: string;
}) {
  if (roster.isPending) return <Skeleton className="h-10 w-full sm:w-72" />;
  if (roster.error) {
    return <PanelError error={roster.error} title="Your panel could not be loaded" />;
  }
  if (!roster.entries.length) {
    return (
      <EmptyState
        icon={UsersRound}
        size="sm"
        title="No patients on your panel"
        description="Patients appear here once an appointment is booked with you."
      />
    );
  }

  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="w-full sm:w-72" aria-label={label}>
        <SelectValue placeholder="Choose a patient" />
      </SelectTrigger>
      <SelectContent>
        {roster.entries.map((entry) => (
          <SelectItem key={entry.patientUserId} value={entry.patientUserId}>
            {entry.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

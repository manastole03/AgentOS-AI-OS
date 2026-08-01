"use client";

import { useCallback, useState } from "react";
import { PageHeader } from "@healthos/ui/page-header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@healthos/ui/tabs";
import { CodingPanel } from "@/components/clinic/coding-panel";
import { DocumentationPanel } from "@/components/clinic/documentation-panel";
import { PatientPanel } from "@/components/clinic/patient-panel";
import { ReferralsPanel } from "@/components/clinic/referrals-panel";
import { SchedulePanel } from "@/components/clinic/schedule-panel";
import { TodayPanel } from "@/components/clinic/today-panel";
import { usePatientRoster } from "@/components/clinic/use-patient-roster";

/**
 * The clinician's day, in the order it is actually worked: what is happening
 * now, who the patient is, what was written down, what it is coded as, who it
 * is being passed to, and when the next opening is.
 *
 * The chosen patient is held here rather than in each tab, so moving from the
 * record to documentation to coding never re-asks who is in the room.
 */
export function ClinicWorkspace() {
  const roster = usePatientRoster();
  const [tab, setTab] = useState("today");
  const [patientId, setPatientId] = useState("");

  const openPatient = useCallback((patientUserId: string) => {
    setPatientId(patientUserId);
    setTab("patients");
  }, []);

  const openDocumentation = useCallback((patientUserId: string) => {
    setPatientId(patientUserId);
    setTab("documentation");
  }, []);

  return (
    <div className="space-y-8">
      <PageHeader
        title="Clinical workspace"
        description="Today's list, the patient record, documentation and coding, referrals, and the availability that feeds patient booking."
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto flex-wrap justify-start">
          <TabsTrigger value="today">Today</TabsTrigger>
          <TabsTrigger value="patients">Patients</TabsTrigger>
          <TabsTrigger value="documentation">Documentation</TabsTrigger>
          <TabsTrigger value="coding">Coding</TabsTrigger>
          <TabsTrigger value="referrals">Referrals</TabsTrigger>
          <TabsTrigger value="schedule">Schedule</TabsTrigger>
        </TabsList>

        <TabsContent value="today">
          <TodayPanel
            onOpenPatient={openPatient}
            onOpenDocumentation={openDocumentation}
          />
        </TabsContent>

        <TabsContent value="patients">
          <PatientPanel
            roster={roster}
            selectedPatientId={patientId}
            onSelectPatient={setPatientId}
          />
        </TabsContent>

        <TabsContent value="documentation">
          <DocumentationPanel
            roster={roster}
            selectedPatientId={patientId}
            onSelectPatient={setPatientId}
          />
        </TabsContent>

        <TabsContent value="coding">
          <CodingPanel
            roster={roster}
            selectedPatientId={patientId}
            onSelectPatient={setPatientId}
          />
        </TabsContent>

        <TabsContent value="referrals">
          <ReferralsPanel
            roster={roster}
            selectedPatientId={patientId}
            onSelectPatient={setPatientId}
          />
        </TabsContent>

        <TabsContent value="schedule">
          <SchedulePanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

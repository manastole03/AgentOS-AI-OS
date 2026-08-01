"use client";

import { useEffect, useState } from "react";
import type {
  AppManifest,
  ApplicationDefinition,
  UserSummary,
} from "@healthos/api-types";
import { AdminWorkspace } from "@/components/portal/admin-workspace";
import { AIAssistant } from "@/components/portal/ai-assistant";
import { DocumentsWorkspace } from "@/components/portal/documents-workspace";
import { NotificationsWorkspace } from "@/components/portal/notifications-workspace";
import { RecordWorkspace } from "@/components/portal/record-workspace";
import { PatientBookingWorkspace } from "@/components/portal/patient-booking-workspace";
import { PatientInsuranceWorkspace } from "@/components/portal/patient-insurance-workspace";
import { authenticatedFetch } from "@/lib/auth";

export function ModuleWorkspace({ slug }: { slug: string }) {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  useEffect(() => {
    Promise.all([
      authenticatedFetch<UserSummary>("/api/v1/auth/session"),
      authenticatedFetch<AppManifest>("/api/v1/app-manifest"),
    ])
      .then(([session, application]) => {
        setUser(session);
        setManifest(application);
      })
      .catch(() => undefined);
  }, []);
  if (!user || !manifest)
    return (
      <div className="space-y-4" aria-label="Loading workspace">
        <div className="h-8 w-56 animate-pulse rounded-lg bg-muted" />
        <div className="h-4 w-full max-w-xl animate-pulse rounded bg-muted" />
        <div className="mt-8 h-72 animate-pulse rounded-2xl bg-muted" />
      </div>
    );
  const moduleDefinition = manifest.modules.find((item) => item.key === slug);
  if (!moduleDefinition)
    return (
      <div className="rounded-2xl border bg-white p-8 text-center shadow-sm">
        <h1 className="text-xl font-semibold">This tool isn’t available</h1>
        <p className="mt-2 text-sm text-muted-foreground">It may not be included in your role or organization’s current setup.</p>
      </div>
    );
  const formDefinition: ApplicationDefinition | undefined = manifest.forms.find(
    (item) => item.key === slug,
  );
  if (slug === "documents") return <DocumentsWorkspace />;
  if (slug === "notifications") return <NotificationsWorkspace />;
  if (slug === "ai_assistant") return <AIAssistant />;
  if (slug === "lab_bookings") return <PatientBookingWorkspace kind="labs" />;
  if (slug === "buy_insurance")
    return <PatientInsuranceWorkspace marketplace />;
  if (slug === "insurance") return <PatientInsuranceWorkspace />;
  if (slug === "appointments" && user?.account_type === "patient")
    return <PatientBookingWorkspace kind="appointments" />;
  if (
    [
      "analytics",
      "audit_logs",
      "user_management",
      "monitoring",
      "system_settings",
    ].includes(slug)
  )
    return <AdminWorkspace slug={slug} />;
  return (
    <RecordWorkspace
      slug={slug}
      moduleDefinition={moduleDefinition}
      formDefinition={formDefinition}
    />
  );
}

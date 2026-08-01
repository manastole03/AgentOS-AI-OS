import type {
  AppManifest,
  ApplicationDefinition,
} from "@healthos/api-types";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bell,
  Bot,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  CreditCard,
  FileText,
  FlaskConical,
  HeartPulse,
  History,
  Landmark,
  LayoutDashboard,
  Pill,
  ReceiptText,
  Settings,
  ShieldCheck,
  Stethoscope,
  Syringe,
  Users,
} from "lucide-react";

const icons: Record<string, LucideIcon> = {
  dashboard: LayoutDashboard,
  medical_history: History,
  vitals: Activity,
  vaccinations: Syringe,
  medications: Pill,
  appointments: CalendarDays,
  lab_reports: FlaskConical,
  lab_bookings: FlaskConical,
  insurance: ShieldCheck,
  buy_insurance: Landmark,
  claims: ReceiptText,
  payments: CreditCard,
  notifications: Bell,
  documents: FileText,
  ai_assistant: Bot,
  patients: Users,
  staff: Users,
  departments: Building2,
  analytics: ChartNoAxesCombined,
  system_settings: Settings,
  visits: Stethoscope,
  health_reminders: HeartPulse,
};

export interface ManifestModule {
  slug: string;
  label: string;
  description: string;
  icon: LucideIcon;
  definition: ApplicationDefinition;
}

export function manifestModules(manifest: AppManifest): ManifestModule[] {
  return manifest.modules.map((definition) => ({
    slug: definition.key,
    label:
      typeof definition.presentation.label === "string"
        ? definition.presentation.label
        : definition.key.replaceAll("_", " "),
    description:
      typeof definition.presentation.description === "string"
        ? definition.presentation.description
        : "Authorized workspace",
    icon: icons[definition.key] ?? FileText,
    definition,
  }));
}

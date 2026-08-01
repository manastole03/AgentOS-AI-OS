import Link from "next/link";
import type { AccountType } from "@healthos/api-types";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@healthos/ui/card";
import { Separator } from "@healthos/ui/separator";
import { ThemeToggle } from "@healthos/ui/theme-toggle";
import { cn } from "@healthos/utils";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  HeartPulse,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

/** Public landing routes, keyed by URL segment. */
export const landingRoutes: Record<string, AccountType> = {
  patient: "patient",
  doctors: "doctor",
  hospital: "hospital",
  insurance: "insurance",
  admin: "admin",
};

interface RoleContent {
  title: string;
  description: string;
  features: string[];
  /** Audience noun used in the feature card heading. */
  audience: string;
  /** Three proof points shown under the hero. */
  proof: Array<{ label: string; value: string }>;
}

const content: Record<AccountType, RoleContent> = {
  patient: {
    title: "Your health and insurance, finally in one place.",
    description:
      "Carry a lifelong health record, find care, know the cost, and manage coverage without bouncing between portals.",
    features: [
      "15-character permanent Health ID",
      "Appointments, labs, telemedicine, and reminders",
      "Plain-language coverage, claims, and policy marketplace",
    ],
    audience: "patients",
    proof: [
      { label: "Health record", value: "Lifelong" },
      { label: "Portals to check", value: "One" },
      { label: "Cost shown", value: "Before care" },
    ],
  },
  doctor: {
    title: "More patient context. Less clinical paperwork.",
    description:
      "Coordinate care with consented records, an accurate schedule, and governed documentation and coding support.",
    features: [
      "Credential verification and availability",
      "Consent-scoped patient timeline",
      "Referrals, documentation, coding, and follow-up",
    ],
    audience: "care teams",
    proof: [
      { label: "Record access", value: "Consent-scoped" },
      { label: "Coding support", value: "Human-reviewed" },
      { label: "Critical results", value: "Tracked" },
    ],
  },
  hospital: {
    title: "A connected operating view for the whole facility.",
    description:
      "Manage clinical capacity, services, scheduling, verification, billing, and revenue operations in one secure workspace.",
    features: [
      "Staff, departments, beds, and resources",
      "Lab and appointment availability",
      "Billing, eligibility, revenue cycle, and reporting",
    ],
    audience: "hospitals",
    proof: [
      { label: "Capacity", value: "Live" },
      { label: "Revenue cycle", value: "End to end" },
      { label: "Reporting", value: "Built in" },
    ],
  },
  insurance: {
    title: "Coverage operations people can understand.",
    description:
      "Distribute policies and run eligibility, claims, prior authorization, estimates, and document workflows with human oversight.",
    features: [
      "Policy marketplace distribution",
      "Eligibility, claims, and prior authorization",
      "Cost estimation and document intelligence",
    ],
    audience: "health plans",
    proof: [
      { label: "Determinations", value: "Auditable" },
      { label: "Benefits", value: "Plain language" },
      { label: "Decision SLA", value: "Monitored" },
    ],
  },
  admin: {
    title: "Trust, oversight, and support for HealthOS.",
    description:
      "Operate the platform with auditable access, monitored dependencies, escalation handling, and controlled configuration.",
    features: [
      "User and role oversight",
      "Audit, analytics, and observability",
      "Customer support and escalation queues",
    ],
    audience: "operators",
    proof: [
      { label: "PHI access", value: "Logged" },
      { label: "Break-glass", value: "Reviewed" },
      { label: "Privacy requests", value: "Tracked" },
    ],
  },
};

/** Each role owns a fixed accent token, so the entry point matches its workspace. */
const roleAccent: Record<AccountType, string> = {
  patient: "text-role-patient",
  doctor: "text-role-doctor",
  hospital: "text-role-hospital",
  insurance: "text-role-insurance",
  admin: "text-role-admin",
};

const roleAccentSurface: Record<AccountType, string> = {
  patient: "border-role-patient/25 bg-role-patient/10",
  doctor: "border-role-doctor/25 bg-role-doctor/10",
  hospital: "border-role-hospital/25 bg-role-hospital/10",
  insurance: "border-role-insurance/25 bg-role-insurance/10",
  admin: "border-role-admin/25 bg-role-admin/10",
};

const roleLabel: Record<AccountType, string> = {
  patient: "Patient",
  doctor: "Care team",
  hospital: "Hospital",
  insurance: "Health plan",
  admin: "Administrator",
};

function ProofPoint({
  icon: Icon,
  label,
  value,
  accent,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  accent: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <Icon className={cn("size-4 shrink-0", accent)} aria-hidden="true" />
      <div className="min-w-0">
        <p className="truncate text-sm font-medium text-foreground">{value}</p>
        <p className="truncate text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

export function RoleLanding({
  accountType,
  route,
}: {
  accountType: AccountType;
  route: string;
}) {
  const item = content[accountType];
  const accent = roleAccent[accountType];

  return (
    <main className="relative min-h-screen bg-background text-foreground">
      <div
        className={cn(
          "pointer-events-none absolute right-0 top-0 size-[34rem] rounded-full blur-3xl",
          roleAccentSurface[accountType],
        )}
        aria-hidden="true"
      />

      <header className="relative border-b bg-background/80 backdrop-blur">
        <div className="container flex h-16 items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 font-semibold">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground">
              <HeartPulse className="size-5" aria-hidden="true" />
            </span>
            HealthOS
          </Link>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link href="/">
                <ArrowLeft className="mr-1.5 size-4" aria-hidden="true" />
                All workspaces
              </Link>
            </Button>
            <ThemeToggle className="size-9" />
          </div>
        </div>
      </header>

      <section className="container relative grid gap-12 py-16 lg:grid-cols-[1.15fr_0.85fr] lg:items-center lg:py-24">
        <div>
          <Badge
            variant="outline"
            className={cn(
              "mb-6 rounded-full px-3 py-1 text-foreground",
              roleAccentSurface[accountType],
            )}
          >
            <ShieldCheck
              className={cn("mr-1.5 size-3.5", accent)}
              aria-hidden="true"
            />
            {roleLabel[accountType]} workspace
          </Badge>
          <h1 className="max-w-3xl text-balance text-4xl font-semibold tracking-tight sm:text-6xl">
            {item.title}
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-8 text-muted-foreground">
            {item.description}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg" className="rounded-full px-7">
              <Link href={`/${route}/login`}>
                Sign in
                <ArrowRight className="ml-2 size-4" aria-hidden="true" />
              </Link>
            </Button>
            <Button
              variant="outline"
              size="lg"
              className="rounded-full px-7"
              asChild
            >
              <Link href={`/${route}/signup`}>
                {accountType === "admin" ? "Access policy" : "Create account"}
              </Link>
            </Button>
          </div>

          <Separator className="my-8 max-w-xl" />

          <div className="grid max-w-xl gap-5 sm:grid-cols-3">
            {item.proof.map((proof) => (
              <ProofPoint
                key={proof.label}
                icon={ShieldCheck}
                label={proof.label}
                value={proof.value}
                accent={accent}
              />
            ))}
          </div>
        </div>

        <Card className="rounded-3xl shadow-sm">
          <CardHeader className="p-7 pb-4">
            <CardTitle className="text-xl">
              Everything you need for {item.audience}
            </CardTitle>
            <p className="pt-2 text-sm leading-6 text-muted-foreground">
              Focused tools, clear next steps, and trusted information in one
              place.
            </p>
          </CardHeader>
          <CardContent className="space-y-3 p-7 pt-3">
            {item.features.map((feature) => (
              <div
                key={feature}
                className="flex gap-3 rounded-2xl border bg-muted/40 p-4"
              >
                <CheckCircle2
                  className={cn("mt-0.5 size-5 shrink-0", accent)}
                  aria-hidden="true"
                />
                <span className="text-sm leading-6 text-foreground">
                  {feature}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </section>

      <footer className="container relative border-t py-6 text-xs text-muted-foreground">
        Your privacy comes first. AI supports navigation and decisions—it never
        replaces qualified care.
      </footer>
    </main>
  );
}

import type { ReactNode } from "react";
import Link from "next/link";
import { CheckCircle2, HeartPulse, LockKeyhole } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";

export function AuthShell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <main className="relative grid min-h-screen place-items-center overflow-hidden bg-background px-4 py-8 text-foreground sm:py-12">
      <div className="hero-glow" aria-hidden="true" />
      <div className="relative w-full max-w-5xl">
        <Link
          href="/"
          className="mb-6 inline-flex items-center gap-2.5 font-bold tracking-tight text-foreground"
        >
          <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm shadow-primary/20">
            <HeartPulse className="size-5" />
          </span>
          HealthOS
        </Link>
        <Card className="grid overflow-hidden border-white/70 shadow-2xl shadow-slate-900/10 lg:grid-cols-[0.82fr_1.18fr]">
          <aside className="relative hidden overflow-hidden bg-slate-950 p-10 text-white lg:flex lg:flex-col lg:justify-between">
            <div className="absolute -right-24 -top-24 size-64 rounded-full bg-teal-400/15 blur-3xl" />
            <div className="relative">
              <p className="text-sm font-semibold text-teal-300">One connected health experience</p>
              <h2 className="mt-4 text-3xl font-semibold leading-tight">Everything you need, with privacy you can trust.</h2>
              <div className="mt-8 space-y-4 text-sm text-slate-300">
                <p className="flex gap-3"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-teal-400" /> Clear, role-specific tools with no unnecessary clutter</p>
                <p className="flex gap-3"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-teal-400" /> Your records and workflows stay connected</p>
                <p className="flex gap-3"><CheckCircle2 className="mt-0.5 size-5 shrink-0 text-teal-400" /> You remain in control of your information</p>
              </div>
            </div>
            <p className="relative mt-12 flex items-center gap-2 text-xs text-slate-400"><LockKeyhole className="size-4 text-teal-400" /> Secure and encrypted by design</p>
          </aside>
          <div className="bg-card px-5 py-8 text-card-foreground sm:px-10 sm:py-10">
            <CardHeader className="p-0 pb-7">
              <CardTitle className="text-2xl leading-tight sm:text-3xl">{title}</CardTitle>
              <CardDescription className="mt-2 text-sm leading-6">{description}</CardDescription>
            </CardHeader>
            <CardContent className="p-0">{children}</CardContent>
          </div>
        </Card>
        <p className="mt-6 text-center text-xs text-muted-foreground">Need help? Contact your HealthOS support team.</p>
      </div>
    </main>
  );
}

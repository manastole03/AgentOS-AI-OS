import Link from "next/link";
import {
  ArrowRight,
  CalendarCheck2,
  Check,
  CircleUserRound,
  Building2,
  HeartHandshake,
  HeartPulse,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";

const roles = [
  {
    href: "/patient",
    title: "For patients",
    description: "Records, appointments, coverage, and costs in one calm place.",
    icon: CircleUserRound,
    color: "bg-teal-50 text-teal-700",
  },
  {
    href: "/doctors",
    title: "For care teams",
    description: "The patient context you need, with less administrative work.",
    icon: Stethoscope,
    color: "bg-sky-50 text-sky-700",
  },
  {
    href: "/hospital",
    title: "For hospitals",
    description: "Coordinate people, capacity, billing, and patient flow.",
    icon: Building2,
    color: "bg-violet-50 text-violet-700",
  },
  {
    href: "/insurance",
    title: "For health plans",
    description: "Simpler coverage operations and clearer member experiences.",
    icon: HeartHandshake,
    color: "bg-amber-50 text-amber-700",
  },
];

export default function HomePage() {
  return (
    <main className="min-h-screen overflow-hidden bg-background">
      <header className="sticky top-0 z-40 border-b bg-background/85 text-foreground backdrop-blur-xl">
        <div className="container flex h-18 items-center justify-between py-3">
          <Link href="/" className="flex items-center gap-2.5 font-bold tracking-tight">
            <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm shadow-primary/20">
              <HeartPulse className="size-5" aria-hidden="true" />
            </span>
            <span className="text-lg">HealthOS</span>
          </Link>
          <nav className="flex items-center gap-2" aria-label="Account navigation">
            <Button variant="ghost" asChild className="hidden sm:inline-flex">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild className="rounded-full px-5 shadow-sm shadow-primary/20">
              <Link href="/signup">Get started <ArrowRight className="ml-2 size-4" /></Link>
            </Button>
          </nav>
        </div>
      </header>

      <section className="relative">
        <div className="hero-glow" aria-hidden="true" />
        <div className="container relative grid gap-14 py-16 lg:grid-cols-[1.05fr_.95fr] lg:items-center lg:py-24">
          <div>
            <Badge className="mb-6 rounded-full border-primary/15 bg-primary/10 px-3 py-1 text-primary hover:bg-primary/10">
              <Sparkles className="mr-1.5 size-3.5" /> Care, made clearer
            </Badge>
            <h1 className="max-w-3xl text-balance text-4xl font-bold leading-[1.08] tracking-[-0.035em] text-foreground sm:text-5xl lg:text-6xl">
              Your whole health journey, connected.
            </h1>
            <p className="mt-6 max-w-xl text-pretty text-lg leading-8 text-muted-foreground">
              HealthOS brings care, records, appointments, and insurance together—so everyone can spend less time navigating systems and more time moving forward.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button size="lg" asChild className="rounded-full px-7 shadow-lg shadow-primary/20">
                <Link href="/signup">Create your free account <ArrowRight className="ml-2 size-4" /></Link>
              </Button>
              <Button size="lg" variant="outline" asChild className="rounded-full bg-card/70 px-7">
                <Link href="/login">I already have an account</Link>
              </Button>
            </div>
            <div className="mt-7 flex flex-wrap gap-x-5 gap-y-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5"><Check className="size-4 text-primary" /> Secure by design</span>
              <span className="flex items-center gap-1.5"><Check className="size-4 text-primary" /> You control access</span>
              <span className="flex items-center gap-1.5"><Check className="size-4 text-primary" /> Plain-language guidance</span>
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-lg lg:mx-0 lg:ml-auto">
            <div className="absolute -inset-8 rounded-full bg-teal-200/30 blur-3xl" />
            <div className="relative rounded-[2rem] border bg-card/90 p-4 text-card-foreground shadow-2xl shadow-slate-900/10 backdrop-blur sm:p-6">
              <div className="flex items-center justify-between border-b pb-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Today</p>
                  <h2 className="mt-1 text-xl font-semibold text-card-foreground">Good morning, Alex</h2>
                </div>
                <span className="grid size-11 place-items-center rounded-full bg-teal-50 text-primary"><HeartPulse className="size-5" /></span>
              </div>
              <div className="mt-5 rounded-2xl bg-slate-950 p-5 text-white">
                <div className="flex items-center gap-3">
                  <span className="grid size-10 place-items-center rounded-xl bg-white/10"><CalendarCheck2 className="size-5 text-teal-300" /></span>
                  <div><p className="text-sm font-medium">Annual checkup</p><p className="mt-0.5 text-xs text-slate-400">Tomorrow · 10:30 AM</p></div>
                </div>
                <div className="mt-5 flex gap-2"><span className="rounded-full bg-teal-400 px-3 py-1.5 text-xs font-semibold text-slate-950">View details</span><span className="rounded-full bg-white/10 px-3 py-1.5 text-xs">Get directions</span></div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-2xl border bg-card p-4"><p className="text-xs text-muted-foreground">Care tasks</p><p className="mt-2 text-2xl font-semibold">2</p><p className="mt-1 text-xs text-warning">Need your attention</p></div>
                <div className="rounded-2xl border bg-card p-4"><p className="text-xs text-muted-foreground">Coverage</p><p className="mt-2 text-sm font-semibold">Active plan</p><p className="mt-2 flex items-center gap-1 text-xs text-success"><ShieldCheck className="size-3.5" /> Verified</p></div>
              </div>
              <div className="mt-4 flex items-center gap-3 rounded-2xl bg-teal-50 p-4 text-sm text-teal-900"><LockKeyhole className="size-5 shrink-0 text-primary" /><span>Your health data is private and protected.</span></div>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y bg-card py-16 text-card-foreground sm:py-20">
        <div className="container">
          <div className="max-w-2xl">
            <p className="text-sm font-semibold text-primary">One platform, built around you</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-card-foreground sm:text-4xl">Choose the workspace that fits your role</h2>
            <p className="mt-4 text-muted-foreground">Every workspace is focused, familiar, and connected to the same trusted source of information.</p>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {roles.map(({ href, title, description, icon: Icon, color }) => (
              <Link key={href} href={href} className="group rounded-2xl border bg-card p-5 transition duration-200 hover:-translate-y-1 hover:border-primary/30 hover:shadow-xl hover:shadow-slate-900/5">
                <span className={`grid size-11 place-items-center rounded-xl ${color}`}><Icon className="size-5" /></span>
                <h3 className="mt-5 font-semibold text-card-foreground">{title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{description}</p>
                <span className="mt-5 flex items-center gap-1 text-sm font-semibold text-primary">Explore workspace <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" /></span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <footer className="bg-slate-950 py-8 text-slate-400">
        <div className="container flex flex-col gap-4 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2 font-semibold text-white"><HeartPulse className="size-5 text-teal-400" /> HealthOS</div>
          <p>AI supports your decisions—it never replaces qualified care.</p>
          <Link href="/admin" className="hover:text-white">Administrator access</Link>
        </div>
      </footer>
    </main>
  );
}

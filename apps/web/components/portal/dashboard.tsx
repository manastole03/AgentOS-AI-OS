"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { PortalDashboard } from "@healthos/api-types";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import {
  Activity,
  ArrowRight,
  Bell,
  CheckCircle2,
  CircleDashed,
  Plus,
  Sparkles,
} from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { PageHeading } from "@/components/portal/page-heading";

export function Dashboard() {
  const [data, setData] = useState<PortalDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    authenticatedFetch<PortalDashboard>("/api/v1/portal/overview")
      .then(setData)
      .catch((value: unknown) =>
        setError(
          value instanceof Error ? value.message : "Unable to load dashboard",
        ),
      );
  }, []);
  if (error)
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
        {error}
      </div>
    );
  if (!data)
    return (
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-32 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    );
  const quickAction = {
    patient: "/portal/appointments",
    doctor: "/portal/ai_assistant",
    hospital: "/portal/beds",
    insurance: "/portal/claims",
    admin: "/portal/monitoring",
  }[data.account_type];
  return (
    <>
      <PageHeading
        eyebrow={`${data.account_type} workspace`}
        title={`Welcome back, ${data.display_name}`}
        description="Here’s what needs your attention and what’s happening across your workspace."
        action={
          <Button asChild>
            <Link href={quickAction}>
              <Plus className="mr-2 size-4" />
              Get started
            </Link>
          </Button>
        }
      />
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {data.metrics.map((metric, index) => (
          <Card key={metric.label} className="overflow-hidden">
            <div
              className={`h-1 ${index === 0 ? "bg-emerald-500" : index === 1 ? "bg-blue-500" : index === 2 ? "bg-amber-500" : "bg-violet-500"}`}
            />
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardDescription>{metric.label}</CardDescription>
                <Activity className="size-4 text-muted-foreground" />
              </div>
              <CardTitle className="text-3xl">
                {metric.value.toLocaleString()}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-xs text-muted-foreground">
                {metric.trend} · synchronized
              </span>
            </CardContent>
          </Card>
        ))}
      </section>
      <section className="mt-6 grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Recent activity</CardTitle>
              <CardDescription>
                Latest records across your authorized workspace
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link href="/portal/documents">View documents</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {data.recent.length ? (
              <div className="divide-y">
                {data.recent.map((item) => (
                  <div key={item.id} className="flex items-center gap-4 py-4">
                    <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
                      <CheckCircle2 className="size-5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">
                        {item.title}
                      </p>
                      <p className="text-xs capitalize text-muted-foreground">
                        {item.category.replaceAll("_", " ")} ·{" "}
                        {new Date(item.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Badge variant="secondary" className="capitalize">
                      {item.status}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyActivity />
            )}
          </CardContent>
        </Card>
        <div className="space-y-6">
          <Card className="bg-slate-950 text-white">
            <CardHeader>
              <div className="mb-2 flex items-center gap-2 text-emerald-400">
                <Sparkles className="size-5" />
                <span className="text-xs font-semibold uppercase tracking-widest">
                  HealthOS intelligence
                </span>
              </div>
              <CardTitle>AI operating system</CardTitle>
              <CardDescription className="text-slate-400">
                Use authorized context, document intelligence, and specialist
                agents.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button className="w-full" asChild>
                <Link href="/portal/ai_assistant">
                  Open AI Assistant <ArrowRight className="ml-2 size-4" />
                </Link>
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Connections{" "}
                <Badge variant="secondary">
                  {Object.values(data.integrations).filter(Boolean).length}/
                  {Object.keys(data.integrations).length}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(data.integrations).map(([name, enabled]) => (
                <div
                  key={name}
                  className="flex items-center justify-between text-sm"
                >
                  <span className="capitalize">{name}</span>
                  <span
                    className={
                      enabled ? "text-emerald-600" : "text-muted-foreground"
                    }
                  >
                    {enabled ? "Connected" : "Local mode"}
                  </span>
                </div>
              ))}
              <div className="flex items-center gap-2 border-t pt-3 text-sm">
                <Bell className="size-4 text-primary" />
                <strong>{data.unread_notifications}</strong>
                <span className="text-muted-foreground">
                  unread notifications
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </>
  );
}

function EmptyActivity() {
  return (
    <div className="grid place-items-center py-14 text-center">
      <CircleDashed className="mb-3 size-8 text-muted-foreground" />
      <p className="text-sm font-medium">Your workspace is ready</p>
      <p className="mt-1 text-xs text-muted-foreground">
        New records and integration activity will appear here.
      </p>
    </div>
  );
}

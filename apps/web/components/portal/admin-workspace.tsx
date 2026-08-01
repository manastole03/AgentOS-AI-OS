"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { Input } from "@healthos/ui/input";
import { Label } from "@healthos/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@healthos/ui/table";
import {
  Activity,
  Database,
  FileClock,
  RefreshCw,
  Server,
  Users,
} from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { moduleCatalog } from "@/lib/portal";
import { PageHeading } from "@/components/portal/page-heading";

type AdminRow = Record<string, unknown>;
interface Monitoring {
  status: string;
  database: string;
  redis: string;
  counts: Record<string, number>;
}

export function AdminWorkspace({ slug }: { slug: string }) {
  const info = moduleCatalog[slug];
  const [rows, setRows] = useState<AdminRow[]>([]);
  const [monitoring, setMonitoring] = useState<Monitoring | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      if (["monitoring", "analytics"].includes(slug))
        setMonitoring(
          await authenticatedFetch<Monitoring>(
            "/api/v1/portal/admin/monitoring",
          ),
        );
      else
        setRows(
          await authenticatedFetch<AdminRow[]>(
            slug === "user_management"
              ? "/api/v1/portal/admin/users"
              : slug === "audit_logs"
                ? "/api/v1/portal/admin/audit"
                : "/api/v1/portal/admin/settings",
          ),
        );
    } catch (value) {
      setError(
        value instanceof Error
          ? value.message
          : "Unable to load administration data",
      );
    }
  }, [slug]);
  useEffect(() => {
    void load();
  }, [load]);
  if (!info) return null;
  return (
    <>
      <PageHeading
        eyebrow="Platform administration"
        title={info.label}
        description={info.description}
        action={
          <Button variant="outline" onClick={() => void load()}>
            <RefreshCw className="mr-2 size-4" />
            Refresh
          </Button>
        }
      />
      {error ? (
        <p className="mb-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {monitoring ? (
        <MonitoringView data={monitoring} analytics={slug === "analytics"} />
      ) : null}
      {slug === "user_management" ? (
        <UsersView rows={rows} reload={load} />
      ) : null}
      {slug === "audit_logs" ? <AuditView rows={rows} /> : null}
      {slug === "system_settings" ? (
        <SettingsView rows={rows} reload={load} />
      ) : null}
    </>
  );
}

function MonitoringView({
  data,
  analytics,
}: {
  data: Monitoring;
  analytics: boolean;
}) {
  const icons = [Users, Activity, FileClock, Database];
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Object.entries(data.counts).map(([key, value], index) => {
          const Icon = icons[index % icons.length];
          return (
            <Card key={key}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardDescription className="capitalize">
                    {key.replaceAll("_", " ")}
                  </CardDescription>
                  <Icon className="size-4 text-primary" />
                </div>
                <CardTitle className="text-3xl">
                  {value.toLocaleString()}
                </CardTitle>
              </CardHeader>
            </Card>
          );
        })}
      </div>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>
            {analytics ? "Platform intelligence" : "Service health"}
          </CardTitle>
          <CardDescription>
            {analytics
              ? "Current cumulative workload across HealthOS."
              : "Live core dependency status."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-3">
          {[
            ["Application", data.status],
            ["PostgreSQL", data.database],
            ["Redis", data.redis],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-center justify-between rounded-lg border p-4"
            >
              <span className="text-sm">{label}</span>
              <Badge variant="secondary" className="capitalize">
                {value}
              </Badge>
            </div>
          ))}
        </CardContent>
      </Card>
    </>
  );
}

function UsersView({
  rows,
  reload,
}: {
  rows: AdminRow[];
  reload: () => Promise<void>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Platform users</CardTitle>
        <CardDescription>{rows.length} accounts</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Verified</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={String(row.id)}>
                  <TableCell className="font-medium">
                    {String(row.email)}
                  </TableCell>
                  <TableCell className="capitalize">
                    {String(row.account_type)}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="capitalize">
                      {String(row.status)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {row.email_verified && row.phone_verified
                      ? "Email + mobile"
                      : "Incomplete"}
                  </TableCell>
                  <TableCell>
                    <select
                      aria-label="Update status"
                      defaultValue={String(row.status)}
                      className="h-9 rounded-md border bg-background px-2 text-sm"
                      onChange={async (event) => {
                        await authenticatedFetch(
                          `/api/v1/portal/admin/users/${String(row.id)}`,
                          {
                            method: "PATCH",
                            body: JSON.stringify({
                              status: event.target.value,
                            }),
                          },
                        );
                        await reload();
                      }}
                    >
                      <option>pending_review</option>
                      <option>active</option>
                      <option>suspended</option>
                      <option>disabled</option>
                    </select>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  );
}

function AuditView({ rows }: { rows: AdminRow[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Immutable audit trail</CardTitle>
        <CardDescription>
          Authentication and portal security events
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {rows.map((row) => (
          <div
            key={String(row.id)}
            className="flex flex-col gap-2 rounded-lg border p-4 sm:flex-row sm:items-center"
          >
            <span className="grid size-9 place-items-center rounded-full bg-muted">
              <FileClock className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {String(row.event_type)}
              </p>
              <p className="text-xs text-muted-foreground">
                {new Date(String(row.created_at)).toLocaleString()}
              </p>
            </div>
            <code className="text-xs text-muted-foreground">
              {String(row.event_hash || row.actor_user_id || "system").slice(
                0,
                12,
              )}
            </code>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function SettingsView({
  rows,
  reload,
}: {
  rows: AdminRow[];
  reload: () => Promise<void>;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const key = String(data.get("key"));
    await authenticatedFetch(`/api/v1/portal/admin/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({
        value: { value: String(data.get("value")) },
        description: String(data.get("description")),
      }),
    });
    event.currentTarget.reset();
    await reload();
  }
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader>
          <CardTitle>Configuration registry</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {rows.map((row) => (
            <div key={String(row.key)} className="rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <code className="text-sm font-semibold">{String(row.key)}</code>
                <Server className="size-4 text-muted-foreground" />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                {String(row.description)}
              </p>
              <pre className="mt-3 overflow-auto rounded bg-muted p-2 text-xs">
                {JSON.stringify(row.value, null, 2)}
              </pre>
            </div>
          ))}
          {!rows.length ? (
            <p className="text-sm text-muted-foreground">
              No runtime overrides. Environment defaults remain active.
            </p>
          ) : null}
        </CardContent>
      </Card>
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Set configuration</CardTitle>
          <CardDescription>Non-secret runtime settings only.</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <Label>Key</Label>
              <Input name="key" required pattern="[a-z0-9_.-]+" />
            </div>
            <div className="space-y-2">
              <Label>Value</Label>
              <Input name="value" required />
            </div>
            <div className="space-y-2">
              <Label>Description</Label>
              <Input name="description" required />
            </div>
            <Button className="w-full">Save setting</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

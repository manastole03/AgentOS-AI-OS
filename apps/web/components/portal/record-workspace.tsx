"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { ApplicationDefinition, PortalRecord } from "@healthos/api-types";
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
import { Textarea } from "@healthos/ui/textarea";
import { CircleDashed, Plus, RefreshCw, Trash2 } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { moduleCatalog, workflowFields } from "@/lib/portal";
import { PageHeading } from "@/components/portal/page-heading";
import { IntegrationActions } from "@/components/portal/integration-actions";

export function RecordWorkspace({
  slug,
  moduleDefinition,
  formDefinition,
}: {
  slug: string;
  moduleDefinition?: ApplicationDefinition;
  formDefinition?: ApplicationDefinition;
}) {
  const catalogInfo = moduleCatalog[slug];
  const info = {
    label:
      (moduleDefinition?.presentation.label as string | undefined) ??
      catalogInfo?.label ??
      slug.replaceAll("_", " "),
    description:
      (moduleDefinition?.presentation.description as string | undefined) ??
      catalogInfo?.description ??
      "Authorized operational workspace",
    noun:
      (moduleDefinition?.presentation.noun as string | undefined) ??
      catalogInfo?.noun ??
      "record",
  };
  const schemaProperties =
    (formDefinition?.schema.properties as
      | Record<
          string,
          { title?: string; type?: string; description?: string; examples?: unknown[] }
        >
      | undefined) ?? {};
  const dynamicFields = Object.entries(schemaProperties).map(([key, value]) => ({
    key,
    label: value.title ?? key.replaceAll("_", " "),
    placeholder:
      value.description ??
      (value.examples?.[0] === undefined ? "" : String(value.examples[0])),
    type: value.type === "number" || value.type === "integer" ? "number" : "text",
  }));
  const activeFields = dynamicFields.length
    ? dynamicFields
    : (workflowFields[slug] ?? []);
  const [items, setItems] = useState<PortalRecord[]>([]);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setItems(
        await authenticatedFetch<PortalRecord[]>(
          `/api/v1/portal/resources/${slug}`,
        ),
      );
    } catch (value) {
      setError(
        value instanceof Error ? value.message : "Unable to load records",
      );
    }
  }, [slug]);
  useEffect(() => {
    void load();
  }, [load]);
  const visibleItems = items.filter((item) =>
    `${item.title} ${item.status} ${String(item.data.notes ?? "")}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const structuredData = Object.fromEntries(
      activeFields.map((field) => [
        field.key,
        String(form.get(field.key) ?? ""),
      ]),
    );
    try {
      await authenticatedFetch(`/api/v1/portal/resources/${slug}`, {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title")),
          status: String(form.get("status") || "active"),
          occurred_at: form.get("occurred_at")
            ? new Date(String(form.get("occurred_at"))).toISOString()
            : null,
          due_at: form.get("due_at")
            ? new Date(String(form.get("due_at"))).toISOString()
            : null,
          amount_cents: form.get("amount")
            ? Math.round(Number(form.get("amount")) * 100)
            : null,
          currency: form.get("amount") ? "USD" : null,
          data: { ...structuredData, notes: String(form.get("notes") || "") },
        }),
      });
      event.currentTarget.reset();
      setCreating(false);
      await load();
    } catch (value) {
      setError(
        value instanceof Error ? value.message : "Unable to save record",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="Workspace"
        title={info.label}
        description={info.description}
        action={
          <div className="flex flex-wrap gap-2">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search records"
              className="w-44"
            />
            <Button variant="outline" onClick={() => void load()}>
              <RefreshCw className="mr-2 size-4" />
              Refresh
            </Button>
            <Button onClick={() => setCreating((value) => !value)}>
              <Plus className="mr-2 size-4" />
              Add {info.noun}
            </Button>
          </div>
        }
      />
      <IntegrationActions module={slug} onComplete={load} />
      {error ? (
        <p className="mb-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {creating ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>New {info.noun}</CardTitle>
            <CardDescription>
              Enter the minimum information now; details can be updated as the
              workflow progresses.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="grid gap-4 md:grid-cols-2">
              <Field label="Title">
                <Input
                  name="title"
                  required
                  maxLength={255}
                  placeholder={`${info.label} title`}
                />
              </Field>
              <Field label="Status">
                <select
                  name="status"
                  className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                >
                  <option value="active">Active</option>
                  <option value="available">Available</option>
                  <option value="booked">Booked</option>
                  <option value="scheduled">Scheduled</option>
                  <option value="pending">Pending</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </Field>
              <Field label="Date">
                <Input name="occurred_at" type="datetime-local" />
              </Field>
              <Field label="Due date">
                <Input name="due_at" type="datetime-local" />
              </Field>
              {[
                "payments",
                "billing",
                "claims",
                "schedule",
                "lab_slots",
                "policies",
              ].includes(slug) ? (
                <Field label="Amount (USD)">
                  <Input name="amount" type="number" min="0" step="0.01" />
                </Field>
              ) : null}
              {activeFields.map((field) => (
                <Field key={field.key} label={field.label}>
                  <Input
                    name={field.key}
                    type={field.type ?? "text"}
                    placeholder={field.placeholder}
                  />
                </Field>
              ))}
              <div className="md:col-span-2">
                <Field label="Notes">
                  <Textarea
                    name="notes"
                    placeholder="Structured workflow notes"
                  />
                </Field>
              </div>
              <div className="flex gap-2 md:col-span-2">
                <Button disabled={busy}>
                  {busy ? "Saving…" : "Save record"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setCreating(false)}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>All {info.label.toLowerCase()}</CardTitle>
          <CardDescription>
            {visibleItems.length} authorized record
            {visibleItems.length === 1 ? "" : "s"}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            {visibleItems.length ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Record</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Details</TableHead>
                    <TableHead className="w-20" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleItems.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell>
                        <p className="font-medium">{item.title}</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          ID {item.id.slice(0, 8).toUpperCase()}
                        </p>
                      </TableCell>
                      <TableCell>
                        <select
                          aria-label="Update status"
                          value={item.status}
                          className="h-9 rounded-md border bg-background px-2 text-sm capitalize"
                          onChange={async (event) => {
                            await authenticatedFetch(
                              `/api/v1/portal/resources/${slug}/${item.id}`,
                              {
                                method: "PATCH",
                                body: JSON.stringify({
                                  status: event.target.value,
                                }),
                              },
                            );
                            await load();
                          }}
                        >
                          {[
                            "active",
                            "available",
                            "booked",
                            "scheduled",
                            "pending",
                            "completed",
                            "cancelled",
                          ].map((status) => (
                            <option key={status}>{status}</option>
                          ))}
                        </select>
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {new Date(
                          item.occurred_at ?? item.created_at,
                        ).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="max-w-sm">
                        <p className="truncate text-muted-foreground">
                          {String(
                            Object.values(item.data).find(Boolean) ||
                              item.external_reference ||
                              "No additional notes",
                          )}
                        </p>
                        {item.amount_cents != null ? (
                          <p className="mt-1 font-medium">
                            {new Intl.NumberFormat("en-US", {
                              style: "currency",
                              currency: item.currency ?? "USD",
                            }).format(item.amount_cents / 100)}
                          </p>
                        ) : null}
                      </TableCell>
                      <TableCell>
                        <Button
                          aria-label="Delete"
                          size="sm"
                          variant="outline"
                          onClick={async () => {
                            if (!window.confirm("Delete this record?")) return;
                            await authenticatedFetch(
                              `/api/v1/portal/resources/${slug}/${item.id}`,
                              { method: "DELETE" },
                            );
                            await load();
                          }}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="grid place-items-center px-6 py-20 text-center">
                <CircleDashed className="mb-3 size-9 text-muted-foreground" />
                <p className="font-medium">No {info.label.toLowerCase()} yet</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Add the first {info.noun} to start this workflow.
                </p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
    </div>
  );
}

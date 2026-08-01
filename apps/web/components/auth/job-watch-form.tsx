"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { JobWatchResponse, JobWatchUpdate } from "@healthos/api-types";
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
import { Textarea } from "@healthos/ui/textarea";
import { authenticatedFetch } from "@/lib/auth";
import { FormError } from "./form-field";

function joinLines(items: string[]): string {
  return items.join("\n");
}

export function JobWatchForm() {
  const [watch, setWatch] = useState<JobWatchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    authenticatedFetch<JobWatchResponse>("/api/v1/users/me/job-watch")
      .then(setWatch)
      .catch((caught) =>
        setError(
          caught instanceof Error
            ? caught.message
            : "Unable to load job watch settings",
        ),
      );
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const titles = String(form.get("titles") ?? "")
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const sourceInputs = String(form.get("source_inputs") ?? "")
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const payload: JobWatchUpdate = {
      enabled: form.get("enabled") === "on",
      email_enabled: form.get("email_enabled") === "on",
      check_interval_minutes: Number(form.get("check_interval_minutes") || 5),
      titles,
      source_inputs: sourceInputs,
    };
    try {
      setWatch(
        await authenticatedFetch<JobWatchResponse>("/api/v1/users/me/job-watch", {
          method: "PATCH",
          body: JSON.stringify(payload),
        }),
      );
      setMessage("Job watch updated.");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Unable to update job watch",
      );
    } finally {
      setPending(false);
    }
  }

  if (!watch) {
    return <p className="text-sm text-muted-foreground">Loading job watch…</p>;
  }

  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Job Watch</CardTitle>
        <CardDescription>
          Paste public Greenhouse, Lever, or Ashby board URLs and HealthOS will
          email you when newly posted roles match your target titles.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={submit}>
          <FormError message={error} />
          {message ? (
            <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
              {message}
            </p>
          ) : null}
          <div className="flex items-center gap-3">
            <input
              id="enabled"
              name="enabled"
              type="checkbox"
              defaultChecked={watch.enabled}
            />
            <Label htmlFor="enabled">Enable job alerts</Label>
          </div>
          <div className="flex items-center gap-3">
            <input
              id="email_enabled"
              name="email_enabled"
              type="checkbox"
              defaultChecked={watch.email_enabled}
            />
            <Label htmlFor="email_enabled">
              Email alerts to {watch.destination_email}
            </Label>
          </div>
          <div className="space-y-2">
            <Label htmlFor="check_interval_minutes">Scan every</Label>
            <Input
              id="check_interval_minutes"
              name="check_interval_minutes"
              type="number"
              min={1}
              max={1440}
              defaultValue={watch.check_interval_minutes}
            />
            <p className="text-xs text-muted-foreground">
              Use 5 minutes for near-real-time alerts.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="titles">Target titles</Label>
            <Textarea
              id="titles"
              name="titles"
              rows={8}
              defaultValue={joinLines(watch.titles)}
            />
            <p className="text-xs text-muted-foreground">
              One title per line. Variants like frontend, backend, and full
              stack are normalized automatically.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="source_inputs">Company job boards</Label>
            <Textarea
              id="source_inputs"
              name="source_inputs"
              rows={8}
              defaultValue={joinLines(watch.sources.map((item) => item.board_url))}
            />
            <p className="text-xs text-muted-foreground">
              One URL per line. Supported examples:
              `https://boards.greenhouse.io/company`,
              `https://jobs.lever.co/company`,
              `https://jobs.ashbyhq.com/company`
            </p>
          </div>
          {watch.sources.length ? (
            <div className="space-y-2 rounded-md border p-3 text-sm">
              <p className="font-medium">Tracked sources</p>
              <ul className="space-y-1 text-muted-foreground">
                {watch.sources.map((item) => (
                  <li key={`${item.source_type}:${item.board_key}`}>
                    {item.company_name} · {item.source_type} · {item.board_key}
                    {item.initial_sync_completed_at
                      ? " · live"
                      : " · baseline pending"}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Save job watch"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

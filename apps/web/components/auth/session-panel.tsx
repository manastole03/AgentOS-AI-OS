"use client";

import { useCallback, useEffect, useState } from "react";
import type { SessionResponse, UserSummary } from "@healthos/api-types";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { authenticatedFetch } from "@/lib/auth";

export function SessionPanel() {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [sessions, setSessions] = useState<SessionResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [currentUser, currentSessions] = await Promise.all([
        authenticatedFetch<UserSummary>("/api/v1/auth/session"),
        authenticatedFetch<SessionResponse[]>("/api/v1/auth/sessions"),
      ]);
      setUser(currentUser);
      setSessions(currentSessions);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to load account",
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (error)
    return (
      <p className="rounded-md bg-red-50 p-4 text-sm text-red-700">{error}</p>
    );
  if (!user)
    return (
      <p className="text-sm text-muted-foreground">
        Loading your secure workspace…
      </p>
    );
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Verified identity and assigned role</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Email</span>
            <span>{user.email}</span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground">Account type</span>
            <Badge variant="secondary">{user.account_type}</Badge>
          </div>
          {user.patient_id ? (
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground">Patient ID</span>
              <code>{user.patient_id}</code>
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Active sessions</CardTitle>
          <CardDescription>
            Revoke devices you no longer recognize
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {sessions.map((session) => (
            <div
              key={session.id}
              className="flex items-start justify-between gap-3 border-b pb-3 last:border-0"
            >
              <div className="min-w-0 text-sm">
                <p className="truncate font-medium">
                  {session.user_agent || "Unknown client"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {new Date(session.created_at).toLocaleString()}{" "}
                  {session.current ? "· Current" : ""}
                </p>
              </div>
              {!session.current ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    await authenticatedFetch(
                      `/api/v1/auth/sessions/${session.id}`,
                      { method: "DELETE" },
                    );
                    await load();
                  }}
                >
                  Revoke
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

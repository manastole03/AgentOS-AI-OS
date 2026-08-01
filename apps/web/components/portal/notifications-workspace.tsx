"use client";

import { useCallback, useEffect, useState } from "react";
import type { PortalNotification } from "@healthos/api-types";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import { Card, CardContent } from "@healthos/ui/card";
import { Bell, Check } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { PageHeading } from "@/components/portal/page-heading";

export function NotificationsWorkspace() {
  const [items, setItems] = useState<PortalNotification[]>([]);
  const load = useCallback(
    async () =>
      setItems(
        await authenticatedFetch<PortalNotification[]>(
          "/api/v1/portal/notifications",
        ),
      ),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  return (
    <>
      <PageHeading
        eyebrow="Inbox"
        title="Notifications"
        description="Clinical, financial, and operational updates from across your care network."
      />
      <div className="space-y-3">
        {items.map((item) => (
          <Card
            key={item.id}
            className={item.read_at ? "opacity-70" : "border-primary/30"}
          >
            <CardContent className="flex gap-4 p-5">
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                <Bell className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium">{item.title}</p>
                  <Badge variant="secondary" className="capitalize">
                    {item.severity}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {item.body}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {new Date(item.created_at).toLocaleString()}
                </p>
              </div>
              {!item.read_at ? (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    await authenticatedFetch(
                      `/api/v1/portal/notifications/${item.id}/read`,
                      { method: "POST" },
                    );
                    await load();
                  }}
                >
                  <Check className="mr-2 size-4" />
                  Read
                </Button>
              ) : null}
            </CardContent>
          </Card>
        ))}
        {!items.length ? (
          <div className="rounded-xl border border-dashed p-16 text-center text-sm text-muted-foreground">
            You are all caught up.
          </div>
        ) : null}
      </div>
    </>
  );
}

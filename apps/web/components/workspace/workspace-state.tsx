"use client";

import type { ReactNode } from "react";
import { Alert } from "@healthos/ui/alert";
import { Skeleton } from "@healthos/ui/skeleton";
import { OctagonAlert } from "lucide-react";
import { apiErrorMessage } from "@/lib/api/client";

/**
 * The three states every workspace panel shares. Kept in one place so a
 * pending panel always reserves the height its content will occupy and a
 * failed read always says what failed rather than rendering an empty table.
 */

export function PanelSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  );
}

export function PanelError({
  error,
  title,
}: {
  error: unknown;
  title: string;
}) {
  return (
    <Alert
      variant="serious"
      icon={<OctagonAlert className="size-4" />}
      title={title}
    >
      {apiErrorMessage(error, "The request did not complete.")}
    </Alert>
  );
}

export interface PanelProps {
  isPending: boolean;
  error: unknown;
  errorTitle: string;
  skeletonRows?: number;
  children: ReactNode;
}

export function Panel({
  isPending,
  error,
  errorTitle,
  skeletonRows,
  children,
}: PanelProps) {
  if (isPending) return <PanelSkeleton rows={skeletonRows} />;
  if (error) return <PanelError error={error} title={errorTitle} />;
  return <>{children}</>;
}

/** Stat rows keep their grid while the numbers are still in flight. */
export function StatRowSkeleton({ tiles = 4 }: { tiles?: number }) {
  return (
    <div
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
      aria-hidden="true"
    >
      {Array.from({ length: tiles }, (_, index) => (
        <Skeleton key={index} className="h-[7.5rem] w-full rounded-xl" />
      ))}
    </div>
  );
}

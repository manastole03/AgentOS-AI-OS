import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import {
  CircleCheck,
  CircleDashed,
  Info,
  OctagonAlert,
  OctagonX,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@healthos/utils";

/**
 * The reserved clinical status tones. These map 1:1 onto the reserved status
 * tokens and are never used as a chart series color.
 */
export type StatusTone =
  "neutral" | "info" | "success" | "warning" | "serious" | "critical";

/**
 * Each tone owns a distinct icon silhouette so the state survives greyscale,
 * colour-vision deficiency and forced-colors mode. The shapes escalate:
 * dashed circle -> circle -> triangle -> octagon -> crossed octagon.
 */
const toneIcons: Record<StatusTone, LucideIcon> = {
  neutral: CircleDashed,
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  serious: OctagonAlert,
  critical: OctagonX,
};

/**
 * Screen-reader prefix so the tone is announced, not just seen.
 */
const toneDescriptions: Record<StatusTone, string> = {
  neutral: "Status",
  info: "Information",
  success: "Success",
  warning: "Warning",
  serious: "Serious",
  critical: "Critical",
};

/**
 * In `soft` the label wears foreground ink and the tone rides on the icon,
 * the tint and the border — tone-coloured small text does not clear 4.5:1
 * against the card in light mode. `solid` uses the paired -foreground tokens
 * and is reserved for the loudest single item in a view.
 */
const statusBadgeVariants = cva(
  "inline-flex max-w-full items-center gap-1.5 rounded-full border font-medium leading-none whitespace-nowrap [&>svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "",
        info: "",
        success: "",
        warning: "",
        serious: "",
        critical: "",
      },
      appearance: {
        soft: "",
        solid: "border-transparent",
      },
      size: {
        sm: "h-5 px-2 text-[0.6875rem] [&>svg]:size-3",
        default: "h-6 px-2.5 text-xs [&>svg]:size-3.5",
      },
    },
    compoundVariants: [
      {
        tone: "neutral",
        appearance: "soft",
        className:
          "border-border bg-muted text-foreground [&>svg]:text-muted-foreground",
      },
      {
        tone: "info",
        appearance: "soft",
        className:
          "border-info/30 bg-info/10 text-foreground [&>svg]:text-info",
      },
      {
        tone: "success",
        appearance: "soft",
        className:
          "border-success/30 bg-success/10 text-foreground [&>svg]:text-success",
      },
      {
        tone: "warning",
        appearance: "soft",
        className:
          "border-warning/35 bg-warning/12 text-foreground [&>svg]:text-warning",
      },
      {
        tone: "serious",
        appearance: "soft",
        className:
          "border-serious/35 bg-serious/12 text-foreground [&>svg]:text-serious",
      },
      {
        tone: "critical",
        appearance: "soft",
        className:
          "border-critical/40 bg-critical/12 text-foreground [&>svg]:text-critical",
      },
      {
        tone: "neutral",
        appearance: "solid",
        className: "bg-secondary text-secondary-foreground",
      },
      {
        tone: "info",
        appearance: "solid",
        className: "bg-info text-info-foreground",
      },
      {
        tone: "success",
        appearance: "solid",
        className: "bg-success text-success-foreground",
      },
      {
        tone: "warning",
        appearance: "solid",
        className: "bg-warning text-warning-foreground",
      },
      {
        tone: "serious",
        appearance: "solid",
        className: "bg-serious text-serious-foreground",
      },
      {
        tone: "critical",
        appearance: "solid",
        className: "bg-critical text-critical-foreground",
      },
    ],
    defaultVariants: {
      tone: "neutral",
      appearance: "soft",
      size: "default",
    },
  },
);

/**
 * Common domain statuses across scheduling, claims, billing and results.
 * Keys are normalised (lower case, non-alphanumerics collapsed to a space).
 */
const domainStatusTones: Record<string, StatusTone> = {
  active: "success",
  approved: "success",
  completed: "success",
  normal: "success",
  resolved: "success",
  pending: "warning",
  "in review": "warning",
  scheduled: "info",
  submitted: "info",
  draft: "neutral",
  cancelled: "neutral",
  canceled: "neutral",
  inactive: "neutral",
  archived: "neutral",
  overdue: "serious",
  abnormal: "serious",
  denied: "critical",
  rejected: "critical",
  failed: "critical",
  critical: "critical",
};

function normalizeStatus(status: string): string {
  return status
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/**
 * Map a domain status string onto a reserved clinical tone. Unknown statuses
 * fall back to `neutral` so an unmapped value never masquerades as healthy or
 * as an emergency.
 */
export function statusTone(status: string): StatusTone {
  return domainStatusTones[normalizeStatus(status)] ?? "neutral";
}

export interface StatusBadgeProps
  extends
    Omit<React.HTMLAttributes<HTMLSpanElement>, "children">,
    VariantProps<typeof statusBadgeVariants> {
  /** Visible text. Required — the badge never communicates state by colour alone. */
  label: string;
  /** Override the tone's default icon. The badge always renders one. */
  icon?: LucideIcon;
  /**
   * Announce the tone name before the label (e.g. "Critical, Denied").
   * Enabled by default; turn it off when surrounding copy already says it.
   */
  announceTone?: boolean;
}

const StatusBadge = React.forwardRef<HTMLSpanElement, StatusBadgeProps>(
  (
    {
      className,
      tone,
      appearance,
      size,
      label,
      icon,
      announceTone = true,
      ...props
    },
    ref,
  ) => {
    const resolvedTone: StatusTone = tone ?? "neutral";
    const Icon = icon ?? toneIcons[resolvedTone];

    return (
      <span
        ref={ref}
        className={cn(
          statusBadgeVariants({ tone: resolvedTone, appearance, size }),
          className,
        )}
        {...props}
      >
        <Icon aria-hidden="true" />
        {announceTone ? (
          <span className="sr-only">{toneDescriptions[resolvedTone]}, </span>
        ) : null}
        <span className="min-w-0 truncate">{label}</span>
      </span>
    );
  },
);
StatusBadge.displayName = "StatusBadge";

export { StatusBadge, statusBadgeVariants };

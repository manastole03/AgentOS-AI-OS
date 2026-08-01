"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import { cn } from "@healthos/utils";

const alertVariants = cva(
  "relative grid w-full grid-cols-[auto_1fr] items-start gap-x-3 gap-y-1 rounded-lg border p-4 text-sm",
  {
    variants: {
      variant: {
        default: "border-border bg-card text-card-foreground",
        info: "border-info bg-info text-info-foreground",
        success: "border-success bg-success text-success-foreground",
        warning: "border-warning bg-warning text-warning-foreground",
        serious: "border-serious bg-serious text-serious-foreground",
        critical: "border-critical bg-critical text-critical-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

type AlertVariant = NonNullable<VariantProps<typeof alertVariants>["variant"]>;

/**
 * Severity is never carried by colour alone: the caller supplies an icon and a
 * title, and screen readers additionally hear this prefix before the title.
 */
const SEVERITY_LABEL: Record<AlertVariant, string | null> = {
  default: null,
  info: "Information",
  success: "Success",
  warning: "Warning",
  serious: "Serious",
  critical: "Critical",
};

const URGENT_VARIANTS: ReadonlySet<AlertVariant> = new Set<AlertVariant>([
  "serious",
  "critical",
]);

export interface AlertProps
  extends
    Omit<React.HTMLAttributes<HTMLDivElement>, "title">,
    VariantProps<typeof alertVariants> {
  /** Required icon slot — the non-colour signal for this alert's severity. */
  icon: React.ReactNode;
  /** Required short summary, rendered as the alert's heading. */
  title: React.ReactNode;
  /** Optional trailing controls (links, buttons) rendered below the body. */
  action?: React.ReactNode;
  /** When provided, renders a dismiss button in the top-right corner. */
  onDismiss?: () => void;
  /** Accessible name for the dismiss button. */
  dismissLabel?: string;
}

export const Alert = React.forwardRef<HTMLDivElement, AlertProps>(
  (
    {
      className,
      variant,
      icon,
      title,
      action,
      onDismiss,
      dismissLabel = "Dismiss alert",
      children,
      ...props
    },
    ref,
  ) => {
    const resolvedVariant: AlertVariant = variant ?? "default";
    const severityLabel = SEVERITY_LABEL[resolvedVariant];
    const urgent = URGENT_VARIANTS.has(resolvedVariant);

    return (
      <div
        ref={ref}
        role={urgent ? "alert" : "status"}
        aria-live={urgent ? "assertive" : "polite"}
        className={cn(alertVariants({ variant }), className)}
        {...props}
      >
        <span
          aria-hidden="true"
          className="flex size-5 items-center justify-center [&>svg]:size-5 [&>svg]:shrink-0"
        >
          {icon}
        </span>

        <div className={cn("min-w-0 space-y-1", onDismiss && "pr-6")}>
          <AlertTitle>
            {severityLabel ? (
              <span className="sr-only">{severityLabel}: </span>
            ) : null}
            {title}
          </AlertTitle>
          {children ? <AlertDescription>{children}</AlertDescription> : null}
          {action ? <div className="pt-2">{action}</div> : null}
        </div>

        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            aria-label={dismissLabel}
            className="absolute right-3 top-3 rounded-sm opacity-80 transition-opacity hover:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current focus-visible:ring-offset-2 focus-visible:ring-offset-transparent"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        ) : null}
      </div>
    );
  },
);
Alert.displayName = "Alert";

export const AlertTitle = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => (
  <p
    ref={ref}
    className={cn("font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
AlertTitle.displayName = "AlertTitle";

export const AlertDescription = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "text-sm leading-relaxed opacity-90 [&_p]:leading-relaxed",
      className,
    )}
    {...props}
  />
));
AlertDescription.displayName = "AlertDescription";

export { alertVariants };

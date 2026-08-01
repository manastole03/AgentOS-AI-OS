"use client";

import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@healthos/utils";

const progressVariants = cva(
  "relative w-full overflow-hidden rounded-full bg-secondary",
  {
    variants: {
      size: {
        sm: "h-1.5",
        default: "h-2.5",
        lg: "h-4",
      },
    },
    defaultVariants: { size: "default" },
  },
);

const progressIndicatorVariants = cva(
  "size-full flex-1 rounded-full transition-transform duration-500 ease-out",
  {
    variants: {
      tone: {
        default: "bg-primary",
        success: "bg-success",
        warning: "bg-warning",
        serious: "bg-serious",
        critical: "bg-critical",
        info: "bg-info",
      },
    },
    defaultVariants: { tone: "default" },
  },
);

/**
 * A progress bar is only meaningful to assistive tech when it is named, so a
 * visible `aria-labelledby` target or an `aria-label` is required.
 */
type ProgressLabelProps =
  | { "aria-label": string; "aria-labelledby"?: never }
  | { "aria-labelledby": string; "aria-label"?: never };

export type ProgressProps = Omit<
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root>,
  "aria-label" | "aria-labelledby"
> &
  VariantProps<typeof progressVariants> &
  VariantProps<typeof progressIndicatorVariants> &
  ProgressLabelProps & {
    /** Classes forwarded to the filled indicator element. */
    indicatorClassName?: string;
  };

const defaultValueLabel = (value: number, max: number): string =>
  `${Math.round((value / max) * 100)}%`;

export const Progress = React.forwardRef<
  React.ComponentRef<typeof ProgressPrimitive.Root>,
  ProgressProps
>(
  (
    {
      className,
      indicatorClassName,
      size,
      tone,
      value = null,
      max = 100,
      getValueLabel = defaultValueLabel,
      ...props
    },
    ref,
  ) => {
    const isIndeterminate = value === null || value === undefined;
    const clamped = isIndeterminate ? 0 : Math.min(Math.max(value, 0), max);

    return (
      <ProgressPrimitive.Root
        ref={ref}
        value={isIndeterminate ? null : clamped}
        max={max}
        getValueLabel={getValueLabel}
        // Radix omits aria-valuetext while indeterminate; announce the wait
        // state explicitly so the bar is never a silent, purely visual cue.
        aria-valuetext={isIndeterminate ? "Loading" : undefined}
        aria-busy={isIndeterminate || undefined}
        className={cn(progressVariants({ size }), className)}
        {...props}
      >
        <ProgressPrimitive.Indicator
          className={cn(
            progressIndicatorVariants({ tone }),
            isIndeterminate && "animate-pulse",
            indicatorClassName,
          )}
          style={{
            transform: isIndeterminate
              ? undefined
              : `translateX(-${100 - (clamped / max) * 100}%)`,
          }}
        />
      </ProgressPrimitive.Root>
    );
  },
);
Progress.displayName = "Progress";

export { progressVariants, progressIndicatorVariants };

import * as React from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  Minus,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@healthos/utils";
import { Card } from "./card";

export type StatDeltaDirection = "up" | "down" | "flat";

/**
 * Whether the movement is good or bad for this metric. Up is not universally
 * good — a rising readmission rate is bad — so the caller states it. Omit it
 * and the delta stays in neutral ink.
 */
export type StatDeltaSentiment = "positive" | "negative" | "neutral";

export interface StatDelta {
  /** Magnitude only; the sign is derived from `direction`. */
  value: string | number;
  direction: StatDeltaDirection;
  /** The comparison period, e.g. "vs last 30 days". */
  label?: string;
  sentiment?: StatDeltaSentiment;
}

const directionIcons: Record<StatDeltaDirection, LucideIcon> = {
  up: ArrowUpRight,
  down: ArrowDownRight,
  flat: Minus,
};

const directionWords: Record<StatDeltaDirection, string> = {
  up: "up",
  down: "down",
  flat: "unchanged",
};

/**
 * Only the arrow carries the sentiment hue. The delta text stays in text ink
 * so it always clears 4.5:1, and direction is already encoded by the arrow
 * and the sign.
 */
const sentimentIconColors: Record<StatDeltaSentiment, string> = {
  positive: "text-success",
  negative: "text-critical",
  neutral: "text-muted-foreground",
};

const MINUS_SIGN = "−";

function formatValue(value: string | number): string {
  return typeof value === "number" ? value.toLocaleString() : value;
}

function formatDelta(
  value: string | number,
  direction: StatDeltaDirection,
): string {
  const text =
    typeof value === "number" ? Math.abs(value).toLocaleString() : value.trim();

  // Respect a sign the caller already baked in.
  if (/^[+\-−]/.test(text)) return text;
  if (direction === "up") return `+${text}`;
  if (direction === "down") return `${MINUS_SIGN}${text}`;
  return text;
}

export interface StatTileProps extends Omit<
  React.HTMLAttributes<HTMLDivElement>,
  "children"
> {
  /** Sentence case, no trailing colon. */
  label: string;
  /** The hero number. */
  value: string | number;
  /** Rendered smaller and muted beside the value, e.g. "mmHg", "%". */
  unit?: string;
  delta?: StatDelta;
  /** Small lucide glyph in the top-right corner. */
  icon?: LucideIcon;
  /** A sparkline or micro-chart. Kept to a fixed-height slot below the value. */
  sparkline?: React.ReactNode;
  /**
   * Accessible name for the sparkline. Without it the sparkline is treated as
   * decorative and hidden — the value and delta already carry the data.
   */
  sparklineLabel?: string;
  /** Turns the whole tile into one link target named by `label`. */
  href?: string;
}

const StatTile = React.forwardRef<HTMLDivElement, StatTileProps>(
  (
    {
      className,
      label,
      value,
      unit,
      delta,
      icon: Icon,
      sparkline,
      sparklineLabel,
      href,
      ...props
    },
    ref,
  ) => {
    const DeltaIcon = delta ? directionIcons[delta.direction] : null;

    return (
      <Card
        ref={ref}
        className={cn(
          "relative flex flex-col gap-2 p-5 shadow-none transition-colors",
          href &&
            "hover:bg-muted/40 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
          className,
        )}
        {...props}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium text-muted-foreground">
            {href ? (
              <a
                className="rounded-sm outline-none after:absolute after:inset-0 after:rounded-[inherit] after:content-['']"
                href={href}
              >
                {label}
              </a>
            ) : (
              label
            )}
          </p>
          {Icon ? (
            <Icon
              aria-hidden="true"
              className="size-4 shrink-0 text-muted-foreground"
            />
          ) : null}
        </div>

        <p className="flex items-baseline gap-1.5">
          <span className="font-mono text-3xl font-semibold tracking-tight tabular text-foreground">
            {formatValue(value)}
          </span>
          {unit ? (
            <span className="text-sm font-medium text-muted-foreground">
              {unit}
            </span>
          ) : null}
        </p>

        {delta && DeltaIcon ? (
          <p className="flex items-center gap-1.5 text-xs">
            <DeltaIcon
              aria-hidden="true"
              className={cn(
                "size-3.5 shrink-0",
                sentimentIconColors[delta.sentiment ?? "neutral"],
              )}
            />
            <span className="sr-only">{directionWords[delta.direction]} </span>
            <span className="font-medium tabular text-foreground">
              {formatDelta(delta.value, delta.direction)}
            </span>
            {delta.label ? (
              <span className="text-muted-foreground">{delta.label}</span>
            ) : null}
          </p>
        ) : null}

        {sparkline ? (
          <div
            aria-hidden={sparklineLabel ? undefined : "true"}
            aria-label={sparklineLabel}
            className="mt-1 h-10 w-full"
            role={sparklineLabel ? "img" : undefined}
          >
            {sparkline}
          </div>
        ) : null}
      </Card>
    );
  },
);
StatTile.displayName = "StatTile";

export { StatTile };

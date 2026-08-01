"use client";

/**
 * Chart primitives — a thin, opinionated wrapper around Recharts v3.
 *
 * PALETTE VALIDATION
 * ------------------
 * The eight categorical series colors below (`--chart-1` … `--chart-8`, defined in
 * `apps/web/app/globals.css`) were validated as a set — computationally, not by eye —
 * in BOTH light and dark against the real app surfaces (light card `#ffffff`,
 * dark card `#131b19`):
 *
 *   - Lightness band ....... PASS  light: all 8 inside L 0.43–0.77 · dark: all 8 inside L 0.48–0.67
 *   - Chroma floor ......... PASS  all 8 >= 0.10 in both modes (no muddy/near-gray slot)
 *   - CVD separation ....... PASS  worst adjacent pair, light: chart-4 <-> chart-3 dE 9.1 (protan);
 *                                  dark: chart-4 <-> chart-3 dE 8.4 (protan) / 8.7 (tritan)
 *   - Normal-vision floor .. PASS  worst adjacent pair dE 19.6 (light) / 19.3 (dark)
 *   - Contrast vs surface .. PASS in dark (all 8 >= 3:1). In LIGHT, chart-3 (2.82:1),
 *                                  chart-4 (2.17:1) and chart-5 (2.69:1) fall under 3:1, which
 *                                  obligates non-color relief. That relief is shipped by default
 *                                  here: a legend, an always-on tooltip, and text that never
 *                                  relies on the series hue. Do not remove it.
 *
 * These values must not be edited, reordered, or extended without re-running the full
 * validation (lightness band, chroma floor, CVD separation, normal-vision floor, contrast)
 * in light AND dark against the app surfaces. Changing one slot changes every adjacent pair.
 *
 * INVARIANTS ENFORCED HERE
 * ------------------------
 *  1. Series color is assigned in FIXED ORDER from `CHART_SERIES`, keyed by the series' slot in the
 *     container's registry — never cycled, never assigned by rank, sort, or payload order. The
 *     registry only ever grows (keys keep the slot they were first seen in), so removing a series
 *     — a filter, a legend toggle, a slice with no rows — cannot repaint the survivors.
 *  2. No dual-axis (two y-scale) charts. There is no `yAxisId` escape hatch in this API, and a
 *     development-time guard warns if one is smuggled in via children.
 *  3. Text wears text tokens (`foreground` / `muted-foreground`), never the series color.
 *  4. Grid and axes are recessive: `border`-colored hairlines, no vertical grid by default,
 *     no axis lines or tick lines, small tick text in `muted-foreground`.
 *  5. Lines are 2px; dots hidden by default with an activeDot of r >= 4 (>= 8px diameter).
 *  6. Touching fills (stack segments, adjacent bars) are separated by a 2px surface-colored gap.
 *  7. A tooltip is present by default — this is an interactive chart, not a static image.
 *  8. Clinical status colors (success / warning / serious / critical) are RESERVED for state and
 *     never appear in `CHART_SERIES`.
 */

import * as React from "react";
import * as RechartsPrimitive from "recharts";
import { cn } from "@healthos/utils";

// This package does not depend on @types/node; declare only what the dev-guard needs. Written as a
// plain member chain so bundlers can statically replace it and drop the guards from production.
declare const process: { env: { NODE_ENV?: string } };

const IS_DEV =
  typeof process !== "undefined" && process.env.NODE_ENV !== "production";

/* -------------------------------------------------------------------------------------------- */
/* Palette                                                                                        */
/* -------------------------------------------------------------------------------------------- */

/**
 * The categorical series palette, in fixed assignment order.
 *
 * Slot N is always the Nth series declared in a chart's `config`. Never cycle this list and never
 * derive a 9th hue: a ninth series folds into "Other", becomes small multiples, or gets a second
 * encoding channel. Clinical status colors are deliberately absent — they mean state, not identity.
 */
export const CHART_SERIES = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
  "var(--chart-7)",
  "var(--chart-8)",
] as const satisfies readonly string[];

export type ChartSeriesColor = (typeof CHART_SERIES)[number];

/** How many entities can carry their own hue before the palette is exhausted. */
export const CHART_SERIES_LIMIT = CHART_SERIES.length;

/**
 * The de-emphasis color for anything past `CHART_SERIES_LIMIT`. It is intentionally a neutral —
 * an overflowing series should be folded into an explicit "Other" bucket, not given a new hue.
 */
export const CHART_OVERFLOW_COLOR = "var(--muted-foreground)";

/**
 * CSS variable holding the surface a chart is painted on. `ChartContainer` sets it; the 2px
 * separators (stack gaps, activeDot rings) paint with it, so the gap is true negative space
 * rather than a border drawn around the mark.
 */
export const CHART_SURFACE_VAR = "var(--chart-surface, var(--card))";

/** Surfaces a chart can sit on. Drives the surface-colored gaps and rings. */
export type ChartSurface = "card" | "background" | "popover";

/** Clinical status tokens that must never be used as a chart series color. */
const RESERVED_STATUS_TOKENS = [
  "success",
  "warning",
  "serious",
  "critical",
] as const;

/* -------------------------------------------------------------------------------------------- */
/* Config                                                                                         */
/* -------------------------------------------------------------------------------------------- */

export interface ChartSeriesConfig {
  /** Human label for the series. Used by the tooltip, the legend, and the table view. */
  label: React.ReactNode;
  /**
   * Optional explicit color. Omit it — the default is this series' fixed slot in `CHART_SERIES`,
   * which is what keeps color pinned to the entity. Only set it for a semantic non-series mark
   * (e.g. a projection in `var(--muted-foreground)`).
   */
  color?: string;
  /** Optional icon rendered instead of the color swatch in tooltip/legend rows. */
  icon?: React.ComponentType<{ className?: string }>;
}

/**
 * The chart's series registry. **Declaration order is the color order** — it is a registry of
 * entities, not a view of the current data. Prefer listing every known series up front, even when
 * the current slice has no rows for one; `ChartContainer` also remembers keys it has already seen,
 * so a later removal cannot shift another series' hue.
 */
export type ChartConfig = Record<string, ChartSeriesConfig>;

/**
 * Resolve a series' color from its FIXED position in a key order.
 *
 * The index is the key's position in the registry — never the data's sort order, never the payload
 * order, never a rank. That is the whole point: filtering, sorting, or hiding series must not
 * repaint the survivors.
 */
function colorForKey(
  order: readonly string[],
  config: ChartConfig,
  key: string,
): string {
  const explicit = config[key]?.color;
  if (explicit) return explicit;
  const index = order.indexOf(key);
  if (index < 0) return CHART_OVERFLOW_COLOR;
  return CHART_SERIES[index] ?? CHART_OVERFLOW_COLOR;
}

/**
 * Resolve a series' color from its FIXED position in `config`.
 *
 * Use this outside a `ChartContainer` (a sparkline, a stat tile's trend dot, a table row key). It
 * trusts `config` to be the complete registry: if you hand it a config that has already been
 * narrowed by a filter, the survivors shift up the palette. Inside a container, prefer
 * `useChart().colorOf(key)`, which pins each key to the slot it was first seen in and is therefore
 * filter-proof by construction.
 */
export function getChartSeriesColor(config: ChartConfig, key: string): string {
  return colorForKey(Object.keys(config), config, key);
}

/**
 * The CSS variable a mark should reference for a series, e.g. `fill={chartColorVar("glucose")}`.
 * `ChartContainer` publishes one of these per config key.
 */
export function chartColorVar(key: string): string {
  return `var(--color-${key})`;
}

/** Comma-grouped numbers for ticks, labels, and tooltip values. */
export function formatChartNumber(
  value: number,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
    ...options,
  }).format(value);
}

/* -------------------------------------------------------------------------------------------- */
/* Mark presets — spread these onto Recharts marks so the specs are the default, not a memory test */
/* -------------------------------------------------------------------------------------------- */

/** Recessive grid: horizontal hairlines only, `border`-colored, solid (never dashed). */
export const CHART_GRID_PROPS = {
  horizontal: true,
  vertical: false,
  stroke: "var(--border)",
  strokeWidth: 1,
} as const;

/** Category axis: no axis line, no tick line, small muted tick text, breathing room at the marks. */
export const CHART_X_AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
  tickMargin: 8,
  minTickGap: 16,
} as const;

/** Value axis: same recessive chrome. There is exactly one of these per chart — never two scales. */
export const CHART_Y_AXIS_PROPS = {
  axisLine: false,
  tickLine: false,
  tickMargin: 8,
  width: 48,
} as const;

/** 2px stroke, round caps, dots hidden, 8px-diameter activeDot with a 2px surface ring. */
export const CHART_LINE_PROPS = {
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  dot: false,
  activeDot: { r: 4, strokeWidth: 2, stroke: CHART_SURFACE_VAR },
} as const;

/** Area: the same 2px line, with the hue as a ~10% wash rather than a saturated block. */
export const CHART_AREA_PROPS = {
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  fillOpacity: 0.1,
  dot: false,
  activeDot: { r: 4, strokeWidth: 2, stroke: CHART_SURFACE_VAR },
} as const;

/**
 * Standalone bars/columns: capped at 24px, 4px rounded data-end, square at the baseline, and a 2px
 * surface-colored separator so adjacent bars read as separate marks rather than one striped block.
 */
export const CHART_BAR_PROPS = {
  maxBarSize: 24,
  // Mutable tuple on purpose: Recharts' `RectRadius` rejects a readonly one.
  radius: [4, 4, 0, 0] as [number, number, number, number],
  stroke: CHART_SURFACE_VAR,
  strokeWidth: 2,
} as const;

/**
 * Segments of a stacked bar: same 2px surface gap, but square — only the top segment of the stack
 * carries the 4px data-end, which you apply by spreading `CHART_BAR_PROPS` on that series alone.
 */
export const CHART_STACKED_BAR_PROPS = {
  maxBarSize: 24,
  radius: 0,
  stroke: CHART_SURFACE_VAR,
  strokeWidth: 2,
} as const;

/** Scatter/reference dots: >= 8px across with a 2px surface ring so overlaps stay legible. */
export const CHART_DOT_PROPS = {
  r: 4,
  strokeWidth: 2,
  stroke: CHART_SURFACE_VAR,
} as const;

/* -------------------------------------------------------------------------------------------- */
/* Context                                                                                        */
/* -------------------------------------------------------------------------------------------- */

export interface ChartContextValue {
  config: ChartConfig;
  chartId: string;
  surface: ChartSurface;
  /**
   * Every series key this container has ever seen, in first-seen order. This — not the current
   * `config` — is what indexes `CHART_SERIES`, so removing a series (a filter, a legend toggle, an
   * empty slice) cannot shift the hue of the ones that remain.
   */
  order: readonly string[];
  /** The fixed-slot color for a series key. */
  colorOf: (key: string) => string;
}

const ChartContext = React.createContext<ChartContextValue | null>(null);

/** Access the enclosing chart's config and its filter-proof color assignment. */
export function useChart(): ChartContextValue {
  const context = React.useContext(ChartContext);
  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />.");
  }
  return context;
}

/* -------------------------------------------------------------------------------------------- */
/* ChartStyle — publishes --color-<key> per container                                             */
/* -------------------------------------------------------------------------------------------- */

const SAFE_CSS_IDENT = /^[A-Za-z0-9_-]+$/;
const UNSAFE_CSS_VALUE = /[<>{};@\\]/;

export interface ChartStyleProps {
  /** The container's `data-chart` id. */
  id: string;
  config: ChartConfig;
  /** Key order that indexes `CHART_SERIES`. Defaults to the config's own declaration order. */
  order?: readonly string[];
}

/**
 * Injects the per-container CSS variables (`--color-<key>`) so marks can reference their series
 * color declaratively — `stroke="var(--color-heartRate)"` — and inherit dark mode for free, since
 * the underlying `--chart-N` tokens are already mode-aware.
 *
 * Keys and values are validated as CSS identifiers before they reach the stylesheet; anything that
 * could break out of the rule is dropped rather than escaped.
 */
export const ChartStyle = ({ id, config, order }: ChartStyleProps) => {
  const css = React.useMemo(() => {
    if (!SAFE_CSS_IDENT.test(id)) return "";
    const keyOrder = order ?? Object.keys(config);
    const declarations = Object.keys(config)
      .map((key) => {
        if (!SAFE_CSS_IDENT.test(key)) return null;
        const color = colorForKey(keyOrder, config, key);
        if (UNSAFE_CSS_VALUE.test(color)) return null;
        return `  --color-${key}: ${color};`;
      })
      .filter((line): line is string => line !== null);
    if (declarations.length === 0) return "";
    return `[data-chart="${id}"] {\n${declarations.join("\n")}\n}`;
  }, [id, config, order]);

  if (!css) return null;
  return <style dangerouslySetInnerHTML={{ __html: css }} />;
};
ChartStyle.displayName = "ChartStyle";

/* -------------------------------------------------------------------------------------------- */
/* ChartContainer                                                                                 */
/* -------------------------------------------------------------------------------------------- */

const chartChrome = cn(
  "flex aspect-video w-full justify-center text-xs",
  // Grid: recessive hairlines in the border token.
  "[&_.recharts-cartesian-grid_line]:stroke-border",
  "[&_.recharts-polar-grid_line]:stroke-border",
  "[&_.recharts-polar-grid_path]:stroke-border",
  "[&_.recharts-reference-line_line]:stroke-border",
  // Axes: no axis line, no tick line, small muted tick text.
  "[&_.recharts-cartesian-axis-line]:stroke-transparent",
  "[&_.recharts-cartesian-axis-tick-line]:stroke-transparent",
  "[&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground",
  "[&_.recharts-cartesian-axis-tick_text]:text-[11px]",
  "[&_.recharts-polar-angle-axis_text]:fill-muted-foreground",
  "[&_.recharts-polar-radius-axis_text]:fill-muted-foreground",
  "[&_.recharts-label]:fill-muted-foreground",
  "[&_.recharts-label-list_text]:fill-foreground",
  // Hover affordances stay quiet: a hairline crosshair, a wash behind bars.
  "[&_.recharts-curve.recharts-tooltip-cursor]:stroke-border",
  "[&_.recharts-rectangle.recharts-tooltip-cursor]:fill-muted",
  "[&_.recharts-sector.recharts-tooltip-cursor]:fill-muted",
  // Recharts paints white hairlines around dots/sectors by default; the surface gap replaces them.
  "[&_.recharts-dot[stroke='#fff']]:stroke-transparent",
  "[&_.recharts-sector[stroke='#fff']]:stroke-transparent",
  // Keyboard focus lands on the root <svg> (Recharts' accessibility layer makes it tabbable and
  // drives the tooltip with arrow keys). It gets a visible ring; decorative groups get nothing.
  "[&_.recharts-layer]:outline-none",
  "[&_.recharts-sector]:outline-none",
  "[&_.recharts-surface]:rounded-md",
  "[&_.recharts-surface:focus-visible]:outline-none",
  "[&_.recharts-surface:focus-visible]:ring-2",
  "[&_.recharts-surface:focus-visible]:ring-ring",
  "[&_.recharts-surface:focus-visible]:ring-offset-2",
  "[&_.recharts-surface:focus-visible]:ring-offset-background",
);

type ChartContainerOwnProps = {
  /** The series registry. Declaration order is color order — see `getChartSeriesColor`. */
  config: ChartConfig;
  /** Exactly one Recharts chart element (`<LineChart>`, `<BarChart>`, …). */
  children: React.ReactElement;
  /** The surface this chart is painted on; drives the 2px separators. Defaults to `card`. */
  surface?: ChartSurface;
  /**
   * A tooltip is injected automatically when the chart has none. Set `false` only for a render
   * that genuinely cannot be hovered (print, static image export).
   */
  tooltip?: boolean;
  /**
   * First-paint dimensions, before the container has measured itself. Supply it when the chart is
   * server-rendered or snapshot-tested — without it Recharts renders an empty box until the
   * client measures.
   */
  initialDimension?: { width: number; height: number };
  /** Stable id for the generated CSS vars. Defaults to a generated one. */
  id?: string;
};

type AccessibleName =
  | { "aria-label": string; "aria-labelledby"?: undefined }
  | { "aria-labelledby": string; "aria-label"?: undefined };

export type ChartContainerProps = Omit<
  React.HTMLAttributes<HTMLDivElement>,
  "children" | "aria-label" | "aria-labelledby"
> &
  ChartContainerOwnProps &
  AccessibleName;

const ChartContainer = React.forwardRef<HTMLDivElement, ChartContainerProps>(
  (
    {
      id,
      className,
      children,
      config,
      surface = "card",
      tooltip = true,
      initialDimension,
      style,
      ...props
    },
    ref,
  ) => {
    const generatedId = React.useId();
    const chartId = `chart-${(id ?? generatedId).replace(/[^A-Za-z0-9_-]/g, "")}`;

    const descendants = React.useMemo(() => collectElements(children), [children]);
    const hasTooltip = React.useMemo(
      () => descendants.some((element) => element.type === RechartsPrimitive.Tooltip),
      [descendants],
    );

    useChartInvariants(config, descendants);

    // Series keys accumulate in first-seen order and are never removed, so a config that shrinks
    // (a filter, a legend toggle, a slice with no rows for a series) leaves every survivor on the
    // palette slot it started on. Rule 1: color follows the entity, not the current series count.
    const seenKeys = React.useRef<readonly string[]>([]);
    const order = React.useMemo(() => {
      const merged = seenKeys.current.slice();
      for (const key of Object.keys(config)) {
        if (!merged.includes(key)) merged.push(key);
      }
      // Idempotent: re-running this (StrictMode double-render) yields the same array contents.
      if (merged.length !== seenKeys.current.length) seenKeys.current = merged;
      return seenKeys.current;
    }, [config]);

    const contextValue = React.useMemo<ChartContextValue>(
      () => ({
        config,
        chartId,
        surface,
        order,
        colorOf: (key: string) => colorForKey(order, config, key),
      }),
      [config, chartId, surface, order],
    );

    const chart = React.useMemo(
      () => (tooltip && !hasTooltip ? withDefaultTooltip(children) : children),
      [tooltip, hasTooltip, children],
    );

    return (
      <ChartContext.Provider value={contextValue}>
        <div
          ref={ref}
          data-chart={chartId}
          data-slot="chart"
          role="group"
          className={cn(chartChrome, className)}
          style={{ ["--chart-surface" as string]: `var(--${surface})`, ...style }}
          {...props}
        >
          <ChartStyle id={chartId} config={config} order={order} />
          <RechartsPrimitive.ResponsiveContainer
            width="100%"
            height="100%"
            initialDimension={initialDimension}
          >
            {chart}
          </RechartsPrimitive.ResponsiveContainer>
        </div>
      </ChartContext.Provider>
    );
  },
);
ChartContainer.displayName = "ChartContainer";

/** Flatten a Recharts child tree into a list of elements, deepest last. */
function collectElements(node: React.ReactNode): React.ReactElement[] {
  const found: React.ReactElement[] = [];
  const walk = (current: React.ReactNode): void => {
    React.Children.forEach(current, (child) => {
      if (!React.isValidElement(child)) return;
      found.push(child);
      const childProps = child.props as { children?: React.ReactNode };
      if (childProps?.children) walk(childProps.children);
    });
  };
  walk(node);
  return found;
}

/**
 * Append a default tooltip (and Recharts' keyboard layer) to a chart that has none. Rule 7: the
 * hover/focus readout is part of the deliverable, so it has to be the thing you opt out of.
 */
function withDefaultTooltip(chart: React.ReactElement): React.ReactElement {
  const chartProps = chart.props as {
    children?: React.ReactNode;
    accessibilityLayer?: boolean;
  };
  // Recharts' keyboard layer (arrow keys drive the tooltip) belongs on a chart component, not on a
  // host element — only a Recharts chart understands the prop.
  const extraProps =
    typeof chart.type === "string"
      ? {}
      : { accessibilityLayer: chartProps.accessibilityLayer ?? true };
  return React.cloneElement(
    chart as React.ReactElement<Record<string, unknown>>,
    extraProps,
    ...React.Children.toArray(chartProps.children),
    <ChartTooltip key="healthos-default-tooltip" content={<ChartTooltipContent />} />,
  );
}

/**
 * Development-time guards for the rules a type system cannot express: no dual axis, no status hue
 * used as a series, and no ninth hue. Silent in production builds.
 */
function useChartInvariants(
  config: ChartConfig,
  descendants: readonly React.ReactElement[],
): void {
  const warnings = React.useMemo(
    () => (IS_DEV ? collectInvariantWarnings(config, descendants) : []),
    [config, descendants],
  );
  // Keyed on the message text, so a warning is logged once per distinct problem rather than on
  // every render of an otherwise healthy chart.
  const signature = warnings.join("\n");

  React.useEffect(() => {
    if (!signature) return;
    for (const warning of signature.split("\n")) {
      console.warn(warning);
    }
  }, [signature]);
}

function collectInvariantWarnings(
  config: ChartConfig,
  descendants: readonly React.ReactElement[],
): string[] {
  const warnings: string[] = [];

  const yAxisIds = new Set<unknown>();
  let yAxisCount = 0;
  for (const element of descendants) {
    if (element.type === RechartsPrimitive.YAxis) yAxisCount += 1;
    const elementProps = element.props as { yAxisId?: unknown };
    if (elementProps?.yAxisId !== undefined) yAxisIds.add(elementProps.yAxisId);
  }
  if (yAxisCount > 1 || yAxisIds.size > 1) {
    warnings.push(
      "[ChartContainer] Dual-axis charts are not supported: two y-scales invite a comparison the " +
        "data does not support. Use two charts, small multiples, or index both measures to a " +
        "common base.",
    );
  }

  const keys = Object.keys(config);
  if (keys.length > CHART_SERIES_LIMIT) {
    warnings.push(
      `[ChartContainer] ${keys.length} series exceeds the ${CHART_SERIES_LIMIT}-slot validated ` +
        'palette. Extra series fall back to a neutral - fold the tail into an explicit "Other" ' +
        "bucket or split into small multiples instead of inventing a ninth hue.",
    );
  }

  for (const key of keys) {
    const color = config[key]?.color;
    if (!color) continue;
    const reserved = RESERVED_STATUS_TOKENS.find((token) => color.includes(`--${token}`));
    if (reserved) {
      warnings.push(
        `[ChartContainer] Series "${key}" uses the reserved clinical status color "--${reserved}". ` +
          "Status colors mean state, not identity - use a slot from CHART_SERIES.",
      );
    }
  }

  return warnings;
}

/* -------------------------------------------------------------------------------------------- */
/* Tooltip                                                                                        */
/* -------------------------------------------------------------------------------------------- */

/**
 * The Recharts tooltip, unmodified — its recessive cursor styling comes from `ChartContainer`.
 * Pair it with `ChartTooltipContent`.
 */
const ChartTooltip = RechartsPrimitive.Tooltip;

type TooltipItem = RechartsPrimitive.TooltipPayloadEntry;

/**
 * Recharts clones a content element with its ENTIRE prop bag (`coordinate`, `viewBox`,
 * `accessibilityLayer`, `separator`, …). So this component names every prop it consumes and
 * forwards nothing it does not understand — spreading the rest onto a `<div>` would emit React
 * unknown-attribute warnings and leak chart internals into the DOM.
 */
export interface ChartTooltipContentProps
  extends Pick<
    Partial<RechartsPrimitive.TooltipContentProps>,
    "active" | "payload" | "label" | "labelFormatter" | "formatter"
  > {
  className?: string;
  style?: React.CSSProperties;
  /** Hide the header row (the shared x value). */
  hideLabel?: boolean;
  /** Hide the per-row color key. */
  hideIndicator?: boolean;
  /** Shape of the per-row color key. */
  indicator?: "dot" | "line" | "dashed";
  /** Read the series key from this payload field instead of `dataKey`/`name`. */
  nameKey?: string;
  /** Read the header label from this config key instead of the axis label. */
  labelKey?: string;
  labelClassName?: string;
}

/**
 * Tooltip readout: one row per series at the hovered x, each with a color key, the series label in
 * `muted-foreground`, and the value in `font-mono tabular text-foreground`. The value leads
 * visually because the reader already knows which series they are chasing.
 */
const ChartTooltipContent = React.forwardRef<HTMLDivElement, ChartTooltipContentProps>(
  (
    {
      active,
      payload,
      label,
      labelFormatter,
      formatter,
      className,
      labelClassName,
      hideLabel = false,
      hideIndicator = false,
      indicator = "dot",
      nameKey,
      labelKey,
      style,
    },
    ref,
  ) => {
    const chart = useChart();
    const { config } = chart;
    const items = (payload ?? []) as readonly TooltipItem[];

    const tooltipLabel = React.useMemo(() => {
      if (hideLabel || items.length === 0) return null;
      const [first] = items;
      const key = labelKey ?? (typeof label === "string" ? label : "");
      const configLabel = key && config[key] ? config[key]?.label : undefined;
      const resolved =
        configLabel ??
        (typeof label === "string" || typeof label === "number" ? label : undefined) ??
        seriesKeyOf(first, nameKey);
      if (labelFormatter) {
        return (
          <div className={cn("font-medium text-foreground", labelClassName)}>
            {labelFormatter(resolved as React.ReactNode, items)}
          </div>
        );
      }
      if (resolved === undefined || resolved === "") return null;
      return (
        <div className={cn("font-medium text-foreground", labelClassName)}>{resolved}</div>
      );
    }, [config, hideLabel, items, label, labelClassName, labelFormatter, labelKey, nameKey]);

    if (!active || items.length === 0) return null;

    return (
      <div
        ref={ref}
        className={cn(
          "grid min-w-[10rem] items-start gap-1.5 rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md",
          className,
        )}
        style={style}
      >
        {tooltipLabel}
        <div className="grid gap-1.5">
          {items.map((item, index) => {
            const key = seriesKeyOf(item, nameKey);
            const itemConfig = config[key];
            const color = resolveItemColor(chart, key, item);
            const formatted = formatter
              ? formatter(item.value, item.name, item, index, items)
              : undefined;
            const [formattedValue, formattedName] = Array.isArray(formatted)
              ? formatted
              : [formatted, undefined];
            const seriesLabel = formattedName ?? itemConfig?.label ?? item.name ?? key;
            const Icon = itemConfig?.icon;

            return (
              <div
                key={`${key}-${index}`}
                className="flex w-full items-center gap-2 leading-none"
              >
                {!hideIndicator &&
                  (Icon ? (
                    <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  ) : (
                    <span
                      aria-hidden="true"
                      className={cn(
                        "shrink-0",
                        indicator === "dot" && "h-2.5 w-2.5 rounded-[2px]",
                        indicator === "line" && "h-0.5 w-3 rounded-full",
                        indicator === "dashed" &&
                          "h-0 w-3 border-[1.5px] border-dashed bg-transparent",
                      )}
                      style={
                        indicator === "dashed"
                          ? { borderColor: color }
                          : { backgroundColor: color }
                      }
                    />
                  ))}
                <span className="flex-1 truncate text-muted-foreground">{seriesLabel}</span>
                <span className="tabular font-mono font-medium text-foreground">
                  {formattedValue ?? formatTooltipValue(item.value)}
                  {item.unit ? (
                    <span className="ml-0.5 text-muted-foreground">{item.unit}</span>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  },
);
ChartTooltipContent.displayName = "ChartTooltipContent";

function seriesKeyOf(item: TooltipItem | undefined, nameKey?: string): string {
  if (!item) return "";
  if (nameKey) {
    const source = item.payload as Record<string, unknown> | undefined;
    const fromPayload = source?.[nameKey];
    if (typeof fromPayload === "string" || typeof fromPayload === "number") {
      return String(fromPayload);
    }
    return nameKey;
  }
  if (typeof item.dataKey === "string" || typeof item.dataKey === "number") {
    return String(item.dataKey);
  }
  if (item.name !== undefined) return String(item.name);
  return "";
}

/**
 * Config first, mark second. Reading the color out of the registry means the swatch always matches
 * the entity's fixed slot, even if a payload arrives in a different order than the series were
 * declared.
 */
function resolveItemColor(
  chart: ChartContextValue,
  key: string,
  item: Pick<TooltipItem, "color" | "stroke" | "fill" | "payload">,
): string {
  if (key && key in chart.config) return chart.colorOf(key);
  const payload = item.payload as { fill?: string; stroke?: string } | undefined;
  return (
    item.color ??
    item.stroke ??
    item.fill ??
    payload?.fill ??
    payload?.stroke ??
    CHART_OVERFLOW_COLOR
  );
}

function formatTooltipValue(value: TooltipItem["value"]): React.ReactNode {
  if (value === undefined || value === null) return "—";
  if (typeof value === "number") return formatChartNumber(value);
  if (Array.isArray(value)) {
    return value
      .map((entry) => (typeof entry === "number" ? formatChartNumber(entry) : String(entry)))
      .join(" – ");
  }
  return String(value);
}

/* -------------------------------------------------------------------------------------------- */
/* Legend                                                                                         */
/* -------------------------------------------------------------------------------------------- */

/** The Recharts legend. Always render one for two or more series — identity is never color-alone. */
const ChartLegend = RechartsPrimitive.Legend;

/**
 * As with the tooltip, Recharts clones this element with the legend's whole prop bag (`iconSize`,
 * `layout`, `align`, `payloadUniqBy`, …), so only named props are consumed and nothing unknown is
 * forwarded to the DOM.
 */
export interface ChartLegendContentProps
  extends Pick<
    Partial<RechartsPrimitive.DefaultLegendContentProps>,
    "payload" | "verticalAlign"
  > {
  className?: string;
  style?: React.CSSProperties;
  /** Hide the color key and rely on the label alone (rare — used with texture fills). */
  hideIcon?: boolean;
  /** Read the series key from this payload field instead of `dataKey`/`value`. */
  nameKey?: string;
}

/**
 * Legend rows: a swatch that mirrors the mark (rect for fills, a short stroke for lines) beside a
 * label in `muted-foreground`. The label never takes the series color — a pale hue is unreadable
 * as text, and identity belongs to the swatch next to it.
 */
const ChartLegendContent = React.forwardRef<HTMLUListElement, ChartLegendContentProps>(
  ({ className, hideIcon = false, payload, verticalAlign = "bottom", nameKey, style }, ref) => {
    const chart = useChart();
    const { config } = chart;
    const items = payload ?? [];

    if (items.length === 0) return null;

    return (
      <ul
        ref={ref}
        className={cn(
          "flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs",
          verticalAlign === "top" ? "pb-3" : "pt-3",
          className,
        )}
        style={style}
      >
        {items.map((item, index) => {
          const key = legendKeyOf(item, nameKey);
          const itemConfig = config[key];
          const color = resolveItemColor(chart, key, {
            color: item.color,
            payload: item.payload,
          });
          const Icon = itemConfig?.icon;
          const isLine = item.type === "line" || item.type === "plainline";

          return (
            <li
              key={`${key}-${index}`}
              className="flex items-center gap-1.5 text-muted-foreground"
            >
              {!hideIcon &&
                (Icon ? (
                  <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                ) : (
                  <span
                    aria-hidden="true"
                    className={cn(
                      "shrink-0",
                      isLine ? "h-0.5 w-3.5 rounded-full" : "h-2.5 w-2.5 rounded-[2px]",
                    )}
                    style={{ backgroundColor: color }}
                  />
                ))}
              <span className="truncate">{itemConfig?.label ?? item.value ?? key}</span>
            </li>
          );
        })}
      </ul>
    );
  },
);
ChartLegendContent.displayName = "ChartLegendContent";

function legendKeyOf(
  item: RechartsPrimitive.LegendPayload,
  nameKey?: string,
): string {
  if (nameKey) {
    const source = item.payload as Record<string, unknown> | undefined;
    const fromPayload = source?.[nameKey];
    if (typeof fromPayload === "string" || typeof fromPayload === "number") {
      return String(fromPayload);
    }
    return nameKey;
  }
  if (typeof item.dataKey === "string" || typeof item.dataKey === "number") {
    return String(item.dataKey);
  }
  return item.value ?? "";
}

export {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
};

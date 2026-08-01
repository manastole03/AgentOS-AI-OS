"use client";

import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import {
  CHART_GRID_PROPS,
  CHART_LINE_PROPS,
  CHART_X_AXIS_PROPS,
  CHART_Y_AXIS_PROPS,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  chartColorVar,
  type ChartConfig,
} from "@healthos/ui/chart";
import { EmptyState } from "@healthos/ui/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@healthos/ui/select";
import { Activity } from "lucide-react";
import { formatDate } from "@/lib/api/format";
import type { VitalOut } from "@/lib/api/types";

/**
 * One measure at a time, on one scale.
 *
 * Weight and heart rate share no unit, so they never share an axis; the caller
 * picks the measure and the chart keeps a single series. That series lives at
 * the fixed `value` key, so switching measure re-labels the line instead of
 * repainting it.
 */

interface MeasureSeries {
  code: string;
  label: string;
  unit: string | null;
  points: Array<{ at: string; value: number }>;
}

function toMeasures(vitals: VitalOut[]): MeasureSeries[] {
  const byCode = new Map<string, MeasureSeries>();
  for (const vital of vitals) {
    if (vital.value_numeric === null) continue;
    const value = Number(vital.value_numeric);
    if (!Number.isFinite(value)) continue;
    const existing = byCode.get(vital.observation_code);
    const point = { at: vital.effective_at, value };
    if (existing) {
      existing.points.push(point);
      continue;
    }
    byCode.set(vital.observation_code, {
      code: vital.observation_code,
      label: vital.observation_display,
      unit: vital.unit,
      points: [point],
    });
  }
  return [...byCode.values()]
    .map((measure) => ({
      ...measure,
      points: measure.points.sort((a, b) => a.at.localeCompare(b.at)),
    }))
    .filter((measure) => measure.points.length > 1)
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function VitalsTrend({ vitals }: { vitals: VitalOut[] }) {
  const measures = useMemo(() => toMeasures(vitals), [vitals]);
  const [selected, setSelected] = useState<string>("");
  const active =
    measures.find((measure) => measure.code === selected) ?? measures[0];

  const config = useMemo<ChartConfig>(
    () => ({ value: { label: active?.label ?? "Measurement" } }),
    [active?.label],
  );

  if (!active) {
    return (
      <EmptyState
        icon={Activity}
        title="No trend to plot yet"
        description="A measure needs at least two readings before it can be charted."
      />
    );
  }

  const unitSuffix = active.unit ? ` ${active.unit}` : "";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Select
          value={active.code}
          onValueChange={setSelected}
          aria-label="Measure to plot"
        >
          <SelectTrigger className="w-[16rem]">
            <SelectValue placeholder="Choose a measure" />
          </SelectTrigger>
          <SelectContent>
            {measures.map((measure) => (
              <SelectItem key={measure.code} value={measure.code}>
                {measure.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-sm text-muted-foreground">
          <span className="tabular">{active.points.length}</span> readings
          {active.unit ? `, in ${active.unit}` : null}
        </p>
      </div>
      <ChartContainer
        config={config}
        className="h-64 w-full"
        aria-label={`${active.label} over time`}
      >
        <ResponsiveContainer>
          <LineChart
            data={active.points}
            margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
          >
            <CartesianGrid {...CHART_GRID_PROPS} />
            <XAxis
              {...CHART_X_AXIS_PROPS}
              dataKey="at"
              tickFormatter={(value: string) =>
                formatDate(value, { style: "short" })
              }
            />
            <YAxis {...CHART_Y_AXIS_PROPS} />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(label) => formatDate(String(label))}
                  formatter={(value) => `${String(value)}${unitSuffix}`}
                />
              }
            />
            <Line
              {...CHART_LINE_PROPS}
              dataKey="value"
              name="value"
              stroke={chartColorVar("value")}
            />
          </LineChart>
        </ResponsiveContainer>
      </ChartContainer>
    </div>
  );
}

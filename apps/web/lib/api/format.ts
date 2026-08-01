/**
 * Presentation helpers shared by every API-backed surface.
 *
 * The API never sends a float for money and never sends a localised date, so
 * formatting is a UI concern that belongs in exactly one place.
 */

/**
 * Formatting is pinned to a single locale so a value rendered on the server
 * matches the value React hydrates on the client.
 */
const DEFAULT_LOCALE = "en-US";

const moneyFormatters = new Map<string, Intl.NumberFormat>();

function moneyFormatter(
  currency: string,
  locale: string,
  fractionDigits: number,
): Intl.NumberFormat {
  const cacheKey = `${locale}|${currency}|${fractionDigits}`;
  let formatter = moneyFormatters.get(cacheKey);
  if (!formatter) {
    formatter = new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
    moneyFormatters.set(cacheKey, formatter);
  }
  return formatter;
}

export interface FormatMoneyOptions {
  locale?: string;
  /** Drop the decimal part — use for axis ticks and dense tables, not totals. */
  compact?: boolean;
  /** Rendered when `cents` is null or undefined. */
  fallback?: string;
}

/**
 * Renders an integer count of minor units. Every money field on the API is
 * `*_cents`; never divide by 100 at a call site.
 */
export function formatMoney(
  cents: number | null | undefined,
  currency: string | null | undefined = "USD",
  options: FormatMoneyOptions = {},
): string {
  const { locale = DEFAULT_LOCALE, compact = false, fallback = "—" } = options;
  if (cents === null || cents === undefined || !Number.isFinite(cents)) {
    return fallback;
  }
  const code = (currency ?? "USD").toUpperCase();
  const units = cents / 100;
  return moneyFormatter(code, locale, compact ? 0 : 2).format(
    compact ? Math.round(units) : units,
  );
}

/** Signed variant for adjustments, refunds and variance columns. */
export function formatMoneyDelta(
  cents: number | null | undefined,
  currency: string | null | undefined = "USD",
  options: FormatMoneyOptions = {},
): string {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) {
    return formatMoney(cents, currency, options);
  }
  const rendered = formatMoney(Math.abs(cents), currency, options);
  if (cents === 0) return rendered;
  return `${cents > 0 ? "+" : "−"}${rendered}`;
}

export type DateStyle = "short" | "medium" | "long";

const DATE_OPTIONS: Record<DateStyle, Intl.DateTimeFormatOptions> = {
  short: { year: "numeric", month: "2-digit", day: "2-digit" },
  medium: { year: "numeric", month: "short", day: "numeric" },
  long: { year: "numeric", month: "long", day: "numeric" },
};

function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === "") return null;
  // A bare `YYYY-MM-DD` parses as UTC midnight, which renders as the previous
  // day west of Greenwich. Pin it to local midnight instead.
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export interface FormatDateOptions {
  locale?: string;
  style?: DateStyle;
  timeZone?: string;
  fallback?: string;
}

/** Formats an ISO date or date-time as a calendar date. */
export function formatDate(
  value: string | number | Date | null | undefined,
  options: FormatDateOptions = {},
): string {
  const {
    locale = DEFAULT_LOCALE,
    style = "medium",
    timeZone,
    fallback = "—",
  } = options;
  const date = toDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat(locale, {
    ...DATE_OPTIONS[style],
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}

/** Formats an ISO date-time as date + time of day. */
export function formatDateTime(
  value: string | number | Date | null | undefined,
  options: FormatDateOptions = {},
): string {
  const {
    locale = DEFAULT_LOCALE,
    style = "medium",
    timeZone,
    fallback = "—",
  } = options;
  const date = toDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat(locale, {
    ...DATE_OPTIONS[style],
    hour: "numeric",
    minute: "2-digit",
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}

/** Time of day only — for slot pickers and reminder rows. */
export function formatTime(
  value: string | number | Date | null | undefined,
  options: Omit<FormatDateOptions, "style"> = {},
): string {
  const { locale = DEFAULT_LOCALE, timeZone, fallback = "—" } = options;
  const date = toDate(value);
  if (!date) return fallback;
  return new Intl.DateTimeFormat(locale, {
    hour: "numeric",
    minute: "2-digit",
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}

/** `9:00 AM – 9:30 AM` for a slot, collapsing the date when it is shared. */
export function formatTimeRange(
  start: string | number | Date | null | undefined,
  end: string | number | Date | null | undefined,
  options: Omit<FormatDateOptions, "style"> = {},
): string {
  const { fallback = "—" } = options;
  const from = toDate(start);
  const to = toDate(end);
  if (!from) return fallback;
  if (!to) return formatTime(from, options);
  return `${formatTime(from, options)} – ${formatTime(to, options)}`;
}

/**
 * Decimal quantities (doses, z-scores, adherence rates) arrive as strings so
 * the backend can keep full precision. Parse only at the render edge.
 */
export function formatDecimal(
  value: string | number | null | undefined,
  options: { locale?: string; digits?: number; fallback?: string } = {},
): string {
  const { locale = DEFAULT_LOCALE, digits = 1, fallback = "—" } = options;
  if (value === null || value === undefined || value === "") return fallback;
  const parsed = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(parsed);
}

/** Renders a 0–1 ratio (adherence, denial rate) as a percentage. */
export function formatPercent(
  ratio: string | number | null | undefined,
  options: { locale?: string; digits?: number; fallback?: string } = {},
): string {
  const { locale = DEFAULT_LOCALE, digits = 0, fallback = "—" } = options;
  if (ratio === null || ratio === undefined || ratio === "") return fallback;
  const parsed = typeof ratio === "number" ? ratio : Number(ratio);
  if (!Number.isFinite(parsed)) return fallback;
  return new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(parsed);
}

/** Whole counts, grouped — pair with the `tabular` class in table cells. */
export function formatCount(
  value: number | null | undefined,
  options: { locale?: string; fallback?: string } = {},
): string {
  const { locale = DEFAULT_LOCALE, fallback = "—" } = options;
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return fallback;
  }
  return new Intl.NumberFormat(locale).format(value);
}

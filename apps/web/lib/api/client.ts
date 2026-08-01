import { toast } from "sonner";

import { ApiError, authenticatedFetch } from "@/lib/auth";

/**
 * Transport layer for the HealthOS API.
 *
 * Every request goes through `authenticatedFetch`, which owns the CSRF header,
 * the 401 refresh-and-retry, and `credentials: "include"`. Nothing here should
 * ever call `fetch` directly.
 *
 * This module is deliberately not marked `"use client"`: the plain fetchers are
 * usable from Server Components, while the hooks that import them are only ever
 * pulled into client bundles.
 */

/** Every route in this layer is mounted under the versioned prefix. */
export const API_BASE = "/api/v1";

export type QueryPrimitive = string | number | boolean;
export type QueryValue =
  | QueryPrimitive
  | readonly QueryPrimitive[]
  | null
  | undefined;
export type QueryParams = Record<string, QueryValue>;

/**
 * Serialises query parameters. Null, undefined and empty-string values are
 * dropped so an unset filter never narrows a result set; arrays repeat the key,
 * which is what FastAPI's `Query(list)` expects.
 */
export function buildQueryString(params?: QueryParams): string {
  if (!params) return "";
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item === null || item === undefined || item === "") continue;
        search.append(key, String(item));
      }
      continue;
    }
    search.append(key, String(value as QueryPrimitive));
  }
  const serialised = search.toString();
  return serialised ? `?${serialised}` : "";
}

/**
 * Template tag that percent-encodes interpolated path segments, so an id
 * containing a slash cannot escape its position in the route.
 *
 * @example route`/labs/orders/${orderId}/cancel`
 */
export function route(
  strings: TemplateStringsArray,
  ...values: Array<string | number>
): string {
  return strings.reduce(
    (accumulator, literal, index) =>
      index < values.length
        ? `${accumulator}${literal}${encodeURIComponent(String(values[index]))}`
        : `${accumulator}${literal}`,
    "",
  );
}

/**
 * A fresh key for an endpoint that accepts `Idempotency-Key`. Generated once per
 * user intent so a network retry replays the stored result instead of creating
 * a second appointment, order or payment.
 */
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export interface RequestOptions {
  query?: QueryParams;
  signal?: AbortSignal;
  headers?: Record<string, string>;
  /** Sent as the `Idempotency-Key` header on write requests that accept one. */
  idempotencyKey?: string;
}

async function request<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = { ...options.headers };
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  const init: RequestInit = { method, headers };
  if (options.signal) init.signal = options.signal;
  if (body !== undefined) init.body = JSON.stringify(body);
  return authenticatedFetch<T>(
    `${API_BASE}${path}${buildQueryString(options.query)}`,
    init,
  );
}

export function get<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>("GET", path, undefined, options);
}

export function post<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>("POST", path, body, options);
}

export function patch<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>("PATCH", path, body, options);
}

export function put<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>("PUT", path, body, options);
}

export function del<T>(
  path: string,
  body?: unknown,
  options?: RequestOptions,
): Promise<T> {
  return request<T>("DELETE", path, body, options);
}

/** The message the API sent, or a caller-supplied fallback. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/**
 * Single surface for mutation failures: the headline states what did not
 * happen, the description carries the server's reason.
 */
export function toastApiError(error: unknown, headline: string): void {
  toast.error(headline, { description: apiErrorMessage(error, headline) });
}

/** Shared list-window parameters — every paginated endpoint accepts these. */
export type PageQuery = {
  limit?: number;
  offset?: number;
};

/**
 * The slice of TanStack Query options a caller may override on a read hook.
 * The query key, fetcher and cache policy stay owned by this layer.
 */
export interface QueryHookOptions {
  /** Defaults to true; set false while a required path parameter is unknown. */
  enabled?: boolean;
  staleTime?: number;
  refetchInterval?: number | false;
}

/**
 * Query-key factory, namespaced per domain.
 *
 * Keys are built longest-prefix-last so a mutation can invalidate a whole
 * resource (`qk.scheduling.appointments()`) or one row
 * (`qk.scheduling.appointment(id)`) with the same call.
 */
export const qk = {
  clinical: {
    all: () => ["clinical"] as const,
    patient: (patientId: string) => ["clinical", "patient", patientId] as const,
    summary: (patientId: string) =>
      ["clinical", "patient", patientId, "summary"] as const,
    timeline: (patientId: string) =>
      ["clinical", "patient", patientId, "timeline"] as const,
    timelineList: (patientId: string, query: PageQuery = {}) =>
      ["clinical", "patient", patientId, "timeline", "list", query] as const,
    allergies: (patientId: string) =>
      ["clinical", "patient", patientId, "allergies"] as const,
    allergyList: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "allergies", "list", query] as const,
    conditions: (patientId: string) =>
      ["clinical", "patient", patientId, "conditions"] as const,
    conditionList: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "conditions", "list", query] as const,
    encounters: (patientId: string) =>
      ["clinical", "patient", patientId, "encounters"] as const,
    encounterList: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "encounters", "list", query] as const,
    vitals: (patientId: string) =>
      ["clinical", "patient", patientId, "vitals"] as const,
    vitalList: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "vitals", "list", query] as const,
    growth: (patientId: string) =>
      ["clinical", "patient", patientId, "growth"] as const,
    growthList: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "growth", "list", query] as const,
    growthPercentiles: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "growth", "percentiles", query] as const,
    immunizations: (patientId: string) =>
      ["clinical", "patient", patientId, "immunizations"] as const,
    immunizationList: (patientId: string, query: object = {}) =>
      [
        "clinical",
        "patient",
        patientId,
        "immunizations",
        "list",
        query,
      ] as const,
    immunizationsDue: (patientId: string, query: object = {}) =>
      ["clinical", "patient", patientId, "immunizations", "due", query] as const,
    certificate: (immunizationId: string) =>
      ["clinical", "immunization", immunizationId, "certificate"] as const,
  },

  medications: {
    all: () => ["medications"] as const,
    patient: (patientId: string) =>
      ["medications", "patient", patientId] as const,
    statements: (patientId: string) =>
      ["medications", "patient", patientId, "statements"] as const,
    statementList: (patientId: string, query: object = {}) =>
      [
        "medications",
        "patient",
        patientId,
        "statements",
        "list",
        query,
      ] as const,
    prescriptions: (patientId: string) =>
      ["medications", "patient", patientId, "prescriptions"] as const,
    prescriptionList: (patientId: string, query: object = {}) =>
      [
        "medications",
        "patient",
        patientId,
        "prescriptions",
        "list",
        query,
      ] as const,
    adherence: (patientId: string) =>
      ["medications", "patient", patientId, "adherence"] as const,
    adherenceReport: (patientId: string, query: object = {}) =>
      ["medications", "patient", patientId, "adherence", query] as const,
    reminders: (patientId: string) =>
      ["medications", "patient", patientId, "reminders"] as const,
    reminderList: (patientId: string, query: object = {}) =>
      ["medications", "patient", patientId, "reminders", "list", query] as const,
  },

  scheduling: {
    all: () => ["scheduling"] as const,
    appointments: () => ["scheduling", "appointments"] as const,
    appointmentList: (query: object = {}) =>
      ["scheduling", "appointments", "list", query] as const,
    appointment: (appointmentId: string) =>
      ["scheduling", "appointments", "detail", appointmentId] as const,
    availability: () => ["scheduling", "availability"] as const,
    availabilityList: (query: object = {}) =>
      ["scheduling", "availability", "list", query] as const,
    providerSchedules: () => ["scheduling", "provider-schedules"] as const,
    providerScheduleList: (query: object = {}) =>
      ["scheduling", "provider-schedules", "list", query] as const,
  },

  labs: {
    all: () => ["labs"] as const,
    tests: () => ["labs", "tests"] as const,
    testList: (query: object = {}) => ["labs", "tests", "list", query] as const,
    facilities: () => ["labs", "facilities"] as const,
    facilityList: (query: object = {}) =>
      ["labs", "facilities", "list", query] as const,
    availability: () => ["labs", "availability"] as const,
    availabilityList: (query: object = {}) =>
      ["labs", "availability", "list", query] as const,
    orders: () => ["labs", "orders"] as const,
    orderList: (query: object = {}) =>
      ["labs", "orders", "list", query] as const,
    order: (orderId: string) => ["labs", "orders", "detail", orderId] as const,
    results: () => ["labs", "results"] as const,
    patientResults: (patientId: string) =>
      ["labs", "results", "patient", patientId] as const,
    patientResultTrend: (patientId: string, query: object = {}) =>
      ["labs", "results", "patient", patientId, query] as const,
    criticalResults: () => ["labs", "results", "critical"] as const,
    criticalResultList: (query: object = {}) =>
      ["labs", "results", "critical", "list", query] as const,
  },

  coverage: {
    all: () => ["coverage"] as const,
    marketplace: () => ["coverage", "marketplace"] as const,
    marketplaceList: (query: object = {}) =>
      ["coverage", "marketplace", "list", query] as const,
    marketplacePlan: (planId: string, query: object = {}) =>
      ["coverage", "marketplace", "plan", planId, query] as const,
    applications: () => ["coverage", "applications"] as const,
    policies: () => ["coverage", "policies"] as const,
    policyList: (query: object = {}) =>
      ["coverage", "policies", "list", query] as const,
    policyExplanation: (policyId: string, query: object = {}) =>
      ["coverage", "policies", "explain", policyId, query] as const,
    loyalty: () => ["coverage", "loyalty"] as const,
    loyaltyBalance: (query: object = {}) =>
      ["coverage", "loyalty", query] as const,
    claimAssistanceAll: () => ["coverage", "claim-assistance"] as const,
    claimAssistance: (query: object = {}) =>
      ["coverage", "claim-assistance", query] as const,
    claims: () => ["coverage", "claims"] as const,
    claimList: (query: object = {}) =>
      ["coverage", "claims", "list", query] as const,
    claim: (claimId: string) =>
      ["coverage", "claims", "detail", claimId] as const,
  },

  payer: {
    all: () => ["payer"] as const,
    analyticsAll: () => ["payer", "analytics"] as const,
    analytics: (query: object = {}) =>
      ["payer", "analytics", "summary", query] as const,
    claims: () => ["payer", "claims"] as const,
    claimList: (query: object = {}) =>
      ["payer", "claims", "list", query] as const,
    costEstimates: () => ["payer", "cost-estimates"] as const,
    costEstimate: (estimateId: string) =>
      ["payer", "cost-estimates", "detail", estimateId] as const,
    eligibility: () => ["payer", "eligibility"] as const,
    plans: () => ["payer", "plans"] as const,
    planList: (query: object = {}) =>
      ["payer", "plans", "list", query] as const,
    planBenefits: (planId: string, query: object = {}) =>
      ["payer", "plans", "detail", planId, "benefits", query] as const,
    plan: (planId: string) => ["payer", "plans", "detail", planId] as const,
    priorAuths: () => ["payer", "prior-authorizations"] as const,
    priorAuthList: (query: object = {}) =>
      ["payer", "prior-authorizations", "list", query] as const,
    products: () => ["payer", "products"] as const,
    productList: (query: object = {}) =>
      ["payer", "products", "list", query] as const,
  },

  operations: {
    all: () => ["operations"] as const,
    platformAnalytics: (query: object = {}) =>
      ["operations", "analytics", "platform", query] as const,
    revenueCycleAll: () => ["operations", "revenue-cycle"] as const,
    revenueCycle: (query: object = {}) =>
      ["operations", "revenue-cycle", "summary", query] as const,
    departments: () => ["operations", "departments"] as const,
    departmentList: (query: object = {}) =>
      ["operations", "departments", "list", query] as const,
    practitioners: () => ["operations", "practitioners"] as const,
    practitionerList: (query: object = {}) =>
      ["operations", "practitioners", "list", query] as const,
    serviceCatalog: () => ["operations", "service-catalog"] as const,
    serviceCatalogList: (query: object = {}) =>
      ["operations", "service-catalog", "list", query] as const,
    encounter: (encounterId: string) =>
      ["operations", "encounters", encounterId] as const,
    encounterCodes: (encounterId: string) =>
      ["operations", "encounters", encounterId, "codes"] as const,
    encounterCodeList: (encounterId: string, query: object = {}) =>
      ["operations", "encounters", encounterId, "codes", "list", query] as const,
    encounterNotes: (encounterId: string) =>
      ["operations", "encounters", encounterId, "notes"] as const,
    encounterNoteList: (encounterId: string, query: object = {}) =>
      ["operations", "encounters", encounterId, "notes", "list", query] as const,
    invoices: () => ["operations", "invoices"] as const,
    invoiceList: (query: object = {}) =>
      ["operations", "invoices", "list", query] as const,
    invoice: (invoiceId: string) =>
      ["operations", "invoices", "detail", invoiceId] as const,
    phiAccess: () => ["operations", "phi-access"] as const,
    phiAccessList: (query: object = {}) =>
      ["operations", "phi-access", "list", query] as const,
    breakGlass: (query: object = {}) =>
      ["operations", "phi-access", "break-glass", query] as const,
    referrals: () => ["operations", "referrals"] as const,
    referralList: (query: object = {}) =>
      ["operations", "referrals", "list", query] as const,
    supportCases: () => ["operations", "support-cases"] as const,
    supportCaseList: (query: object = {}) =>
      ["operations", "support-cases", "list", query] as const,
    dataSubjectRequests: () => ["operations", "data-subject-requests"] as const,
    dataSubjectRequestList: (query: object = {}) =>
      ["operations", "data-subject-requests", "list", query] as const,
  },
} as const;

export { ApiError };

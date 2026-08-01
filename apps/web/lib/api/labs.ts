import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { toast } from "sonner";

import {
  get,
  newIdempotencyKey,
  post,
  qk,
  route,
  toastApiError,
  type PageQuery,
  type QueryHookOptions,
} from "./client";
import type {
  CriticalResultOut,
  LabFacilityOut,
  LabOrderCreate,
  LabOrderDetail,
  LabOrderOut,
  LabResultOut,
  LabResultsCreate,
  LabTestOut,
  OrderCancel,
  Page,
  PatientResultTrend,
  ResultAcknowledge,
  SlotAvailabilityOut,
  SpecimenCreate,
  SpecimenOut,
} from "./types";

/**
 * Test catalogue, collection facilities, order lifecycle, specimens and
 * results — including the critical-result queue.
 *
 * Backend router: `/api/v1/labs`.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

export type LabTestListQuery = PageQuery & {
  search?: string | null;
  code?: string | null;
  panel_code?: string | null;
  specimen_type_code?: string | null;
  fasting_required?: boolean | null;
  max_turnaround_hours?: number | null;
  include_inactive?: boolean;
};

export type LabFacilityListQuery = PageQuery & {
  search?: string | null;
  city?: string | null;
  home_collection?: boolean | null;
  include_inactive?: boolean;
};

export type LabAvailabilityQuery = PageQuery & {
  /** Repeated `test_ids` — availability is scored against the whole basket. */
  test_ids?: readonly string[] | null;
  from?: string | null;
  to?: string | null;
  facility_id?: string | null;
};

export type LabOrderListQuery = PageQuery & {
  status?: string | null;
  patient_id?: string | null;
  facility_id?: string | null;
  from?: string | null;
  to?: string | null;
};

export type PatientResultsQuery = {
  /** Repeated LOINC codes; one trend series is returned per code. */
  code?: readonly string[] | null;
  since?: string | null;
  until?: string | null;
  limit?: number;
};

export type CriticalResultQuery = PageQuery & {
  facility_id?: string | null;
  ordering_provider_user_id?: string | null;
  since?: string | null;
};

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/labs/tests */
export function fetchLabTests(
  query: LabTestListQuery = {},
  signal?: AbortSignal,
): Promise<Page<LabTestOut>> {
  return get<Page<LabTestOut>>("/labs/tests", { query, signal });
}

/** GET /api/v1/labs/facilities */
export function fetchLabFacilities(
  query: LabFacilityListQuery = {},
  signal?: AbortSignal,
): Promise<Page<LabFacilityOut>> {
  return get<Page<LabFacilityOut>>("/labs/facilities", { query, signal });
}

/** GET /api/v1/labs/availability */
export function fetchLabAvailability(
  query: LabAvailabilityQuery = {},
  signal?: AbortSignal,
): Promise<Page<SlotAvailabilityOut>> {
  return get<Page<SlotAvailabilityOut>>("/labs/availability", {
    query,
    signal,
  });
}

/** GET /api/v1/labs/orders */
export function fetchLabOrders(
  query: LabOrderListQuery = {},
  signal?: AbortSignal,
): Promise<Page<LabOrderOut>> {
  return get<Page<LabOrderOut>>("/labs/orders", { query, signal });
}

/** GET /api/v1/labs/orders/{order_id} */
export function fetchLabOrder(
  orderId: string,
  signal?: AbortSignal,
): Promise<LabOrderDetail> {
  return get<LabOrderDetail>(route`/labs/orders/${orderId}`, { signal });
}

/**
 * POST /api/v1/labs/orders
 *
 * Idempotent: a retry with the same key replays the stored order rather than
 * charging the patient twice.
 */
export function createLabOrder(
  body: LabOrderCreate,
  idempotencyKey: string = newIdempotencyKey(),
): Promise<LabOrderDetail> {
  return post<LabOrderDetail>("/labs/orders", body, { idempotencyKey });
}

/** POST /api/v1/labs/orders/{order_id}/cancel */
export function cancelLabOrder(
  orderId: string,
  body: OrderCancel = {},
): Promise<LabOrderDetail> {
  return post<LabOrderDetail>(route`/labs/orders/${orderId}/cancel`, body);
}

/** POST /api/v1/labs/orders/{order_id}/specimens */
export function collectSpecimen(
  orderId: string,
  body: SpecimenCreate,
): Promise<SpecimenOut> {
  return post<SpecimenOut>(route`/labs/orders/${orderId}/specimens`, body);
}

/** POST /api/v1/labs/orders/{order_id}/results */
export function postLabResults(
  orderId: string,
  body: LabResultsCreate,
): Promise<LabResultOut[]> {
  return post<LabResultOut[]>(route`/labs/orders/${orderId}/results`, body);
}

/** GET /api/v1/labs/patients/{patient_id}/results */
export function fetchPatientResults(
  patientId: string,
  query: PatientResultsQuery = {},
  signal?: AbortSignal,
): Promise<PatientResultTrend> {
  return get<PatientResultTrend>(route`/labs/patients/${patientId}/results`, {
    query,
    signal,
  });
}

/** GET /api/v1/labs/results/critical */
export function fetchCriticalResults(
  query: CriticalResultQuery = {},
  signal?: AbortSignal,
): Promise<Page<CriticalResultOut>> {
  return get<Page<CriticalResultOut>>("/labs/results/critical", {
    query,
    signal,
  });
}

/** POST /api/v1/labs/results/{result_id}/acknowledge */
export function acknowledgeResult(
  resultId: string,
  body: ResultAcknowledge = {},
): Promise<LabResultOut> {
  return post<LabResultOut>(route`/labs/results/${resultId}/acknowledge`, body);
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useLabTests(
  query: LabTestListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<LabTestOut>> {
  return useQuery({
    queryKey: qk.labs.testList(query),
    queryFn: ({ signal }) => fetchLabTests(query, signal),
    enabled: options.enabled ?? true,
    // The catalogue changes on a release cadence, not a request cadence.
    staleTime: options.staleTime ?? 5 * 60_000,
  });
}

export function useLabFacilities(
  query: LabFacilityListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<LabFacilityOut>> {
  return useQuery({
    queryKey: qk.labs.facilityList(query),
    queryFn: ({ signal }) => fetchLabFacilities(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime ?? 5 * 60_000,
  });
}

export function useLabAvailability(
  query: LabAvailabilityQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<SlotAvailabilityOut>> {
  return useQuery({
    queryKey: qk.labs.availabilityList(query),
    queryFn: ({ signal }) => fetchLabAvailability(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime ?? 10_000,
    refetchInterval: options.refetchInterval,
  });
}

export function useLabOrders(
  query: LabOrderListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<LabOrderOut>> {
  return useQuery({
    queryKey: qk.labs.orderList(query),
    queryFn: ({ signal }) => fetchLabOrders(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useLabOrder(
  orderId: string,
  options: QueryHookOptions = {},
): UseQueryResult<LabOrderDetail> {
  return useQuery({
    queryKey: qk.labs.order(orderId),
    queryFn: ({ signal }) => fetchLabOrder(orderId, signal),
    enabled: (options.enabled ?? true) && Boolean(orderId),
    staleTime: options.staleTime,
  });
}

export function usePatientResults(
  patientId: string,
  query: PatientResultsQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<PatientResultTrend> {
  return useQuery({
    queryKey: qk.labs.patientResultTrend(patientId, query),
    queryFn: ({ signal }) => fetchPatientResults(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useCriticalResults(
  query: CriticalResultQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<CriticalResultOut>> {
  return useQuery({
    queryKey: qk.labs.criticalResultList(query),
    queryFn: ({ signal }) => fetchCriticalResults(query, signal),
    enabled: options.enabled ?? true,
    // A critical value is time-bound; this queue must not go stale on screen.
    staleTime: options.staleTime ?? 0,
    refetchInterval: options.refetchInterval ?? 60_000,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreateLabOrder(): UseMutationResult<
  LabOrderDetail,
  Error,
  LabOrderCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LabOrderCreate) => createLabOrder(body),
    onSuccess: (order) => {
      toast.success("Lab order placed", { description: order.order_number });
      // The booked collection slot is no longer offerable.
      void queryClient.invalidateQueries({ queryKey: qk.labs.availability() });
      void queryClient.invalidateQueries({ queryKey: qk.labs.orders() });
      void queryClient.invalidateQueries({ queryKey: qk.operations.invoices() });
    },
    onError: (error) => toastApiError(error, "Could not place the lab order"),
  });
}

export interface CancelLabOrderVariables {
  orderId: string;
  body?: OrderCancel;
}

export function useCancelLabOrder(): UseMutationResult<
  LabOrderDetail,
  Error,
  CancelLabOrderVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, body }: CancelLabOrderVariables) =>
      cancelLabOrder(orderId, body ?? {}),
    onSuccess: (order) => {
      toast.success("Lab order cancelled", { description: order.order_number });
      // Cancelling releases the collection slot.
      void queryClient.invalidateQueries({ queryKey: qk.labs.availability() });
      void queryClient.invalidateQueries({ queryKey: qk.labs.orders() });
      queryClient.setQueryData(qk.labs.order(order.id), order);
      void queryClient.invalidateQueries({ queryKey: qk.operations.invoices() });
    },
    onError: (error) => toastApiError(error, "Could not cancel the lab order"),
  });
}

export interface CollectSpecimenVariables {
  orderId: string;
  body: SpecimenCreate;
}

export function useCollectSpecimen(): UseMutationResult<
  SpecimenOut,
  Error,
  CollectSpecimenVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, body }: CollectSpecimenVariables) =>
      collectSpecimen(orderId, body),
    onSuccess: (specimen) => {
      toast.success("Specimen accessioned", {
        description: specimen.accession_number,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.labs.order(specimen.lab_order_id),
      });
      void queryClient.invalidateQueries({ queryKey: qk.labs.orders() });
    },
    onError: (error) => toastApiError(error, "Could not record the specimen"),
  });
}

export interface PostLabResultsVariables {
  orderId: string;
  body: LabResultsCreate;
}

export function usePostLabResults(): UseMutationResult<
  LabResultOut[],
  Error,
  PostLabResultsVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, body }: PostLabResultsVariables) =>
      postLabResults(orderId, body),
    onSuccess: (results, variables) => {
      const critical = results.filter((result) => result.is_critical);
      if (critical.length > 0) {
        toast.warning(
          `${results.length} results filed — ${critical.length} critical`,
          { description: critical[0].test_display },
        );
      } else {
        toast.success(`${results.length} results filed`);
      }
      void queryClient.invalidateQueries({
        queryKey: qk.labs.order(variables.orderId),
      });
      void queryClient.invalidateQueries({ queryKey: qk.labs.orders() });
      void queryClient.invalidateQueries({ queryKey: qk.labs.results() });
      const patientId = results[0]?.patient_user_id;
      if (patientId) {
        void queryClient.invalidateQueries({
          queryKey: qk.clinical.timeline(patientId),
        });
      }
    },
    onError: (error) => toastApiError(error, "Could not file the results"),
  });
}

export interface AcknowledgeResultVariables {
  resultId: string;
  body?: ResultAcknowledge;
}

export function useAcknowledgeResult(): UseMutationResult<
  LabResultOut,
  Error,
  AcknowledgeResultVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ resultId, body }: AcknowledgeResultVariables) =>
      acknowledgeResult(resultId, body ?? {}),
    onSuccess: (result) => {
      toast.success("Result acknowledged", {
        description: result.test_display,
      });
      // Acknowledgement removes the row from the critical queue.
      void queryClient.invalidateQueries({
        queryKey: qk.labs.criticalResults(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.labs.patientResults(result.patient_user_id),
      });
      if (result.lab_order_id) {
        void queryClient.invalidateQueries({
          queryKey: qk.labs.order(result.lab_order_id),
        });
      }
    },
    onError: (error) =>
      toastApiError(error, "Could not acknowledge the result"),
  });
}

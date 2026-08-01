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
import { formatMoney } from "./format";
import type {
  AppointmentCreate,
  AppointmentResponse,
  AppointmentStatus,
  AvailabilitySlot,
  BookingResponse,
  CancelRequest,
  EncounterChannel,
  Page,
  PaymentResponse,
  ProviderScheduleCreate,
  ProviderScheduleResponse,
  RescheduleRequest,
  SchedulingPaymentCreate,
  SlotGenerationRequest,
  SlotGenerationResult,
  TelehealthCreate,
  TelehealthSessionResponse,
} from "./types";

/**
 * Provider availability, appointment lifecycle, appointment payment and
 * telehealth sessions.
 *
 * Backend router: `/api/v1/scheduling`.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

export type AvailabilityQuery = PageQuery & {
  specialty?: string | null;
  organization_id?: string | null;
  /** ISO-8601 window start. */
  from?: string | null;
  /** ISO-8601 window end. */
  to?: string | null;
  mode?: EncounterChannel | null;
};

export type AppointmentListQuery = PageQuery & {
  status?: AppointmentStatus | null;
  from?: string | null;
  to?: string | null;
};

export type ProviderScheduleListQuery = PageQuery & {
  provider_user_id?: string | null;
  organization_id?: string | null;
  is_active?: boolean | null;
};

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/scheduling/providers/availability */
export function fetchProviderAvailability(
  query: AvailabilityQuery = {},
  signal?: AbortSignal,
): Promise<Page<AvailabilitySlot>> {
  return get<Page<AvailabilitySlot>>("/scheduling/providers/availability", {
    query,
    signal,
  });
}

/** GET /api/v1/scheduling/appointments */
export function fetchAppointments(
  query: AppointmentListQuery = {},
  signal?: AbortSignal,
): Promise<Page<AppointmentResponse>> {
  return get<Page<AppointmentResponse>>("/scheduling/appointments", {
    query,
    signal,
  });
}

/** GET /api/v1/scheduling/appointments/{appointment_id} */
export function fetchAppointment(
  appointmentId: string,
  signal?: AbortSignal,
): Promise<AppointmentResponse> {
  return get<AppointmentResponse>(
    route`/scheduling/appointments/${appointmentId}`,
    { signal },
  );
}

/**
 * POST /api/v1/scheduling/appointments
 *
 * Idempotent: a retry with the same key replays the stored booking instead of
 * consuming a second slot.
 */
export function bookAppointment(
  body: AppointmentCreate,
  idempotencyKey: string = newIdempotencyKey(),
): Promise<BookingResponse> {
  return post<BookingResponse>("/scheduling/appointments", body, {
    idempotencyKey,
  });
}

/** POST /api/v1/scheduling/appointments/{appointment_id}/cancel */
export function cancelAppointment(
  appointmentId: string,
  body: CancelRequest = {},
): Promise<AppointmentResponse> {
  return post<AppointmentResponse>(
    route`/scheduling/appointments/${appointmentId}/cancel`,
    body,
  );
}

/** POST /api/v1/scheduling/appointments/{appointment_id}/reschedule */
export function rescheduleAppointment(
  appointmentId: string,
  body: RescheduleRequest,
): Promise<AppointmentResponse> {
  return post<AppointmentResponse>(
    route`/scheduling/appointments/${appointmentId}/reschedule`,
    body,
  );
}

/**
 * POST /api/v1/scheduling/appointments/{appointment_id}/pay
 *
 * The key travels in both the `Idempotency-Key` header and the payment body so
 * the processor and the ledger agree on the same attempt.
 */
export function payForAppointment(
  appointmentId: string,
  body: SchedulingPaymentCreate = {},
  idempotencyKey: string = newIdempotencyKey(),
): Promise<PaymentResponse> {
  return post<PaymentResponse>(
    route`/scheduling/appointments/${appointmentId}/pay`,
    { ...body, idempotency_key: body.idempotency_key ?? idempotencyKey },
    { idempotencyKey },
  );
}

/** POST /api/v1/scheduling/appointments/{appointment_id}/telehealth */
export function createTelehealthSession(
  appointmentId: string,
  body: TelehealthCreate = {},
): Promise<TelehealthSessionResponse> {
  return post<TelehealthSessionResponse>(
    route`/scheduling/appointments/${appointmentId}/telehealth`,
    body,
  );
}

/** GET /api/v1/scheduling/provider-schedules */
export function fetchProviderSchedules(
  query: ProviderScheduleListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ProviderScheduleResponse>> {
  return get<Page<ProviderScheduleResponse>>("/scheduling/provider-schedules", {
    query,
    signal,
  });
}

/** POST /api/v1/scheduling/provider-schedules */
export function createProviderSchedule(
  body: ProviderScheduleCreate,
): Promise<ProviderScheduleResponse> {
  return post<ProviderScheduleResponse>("/scheduling/provider-schedules", body);
}

/** POST /api/v1/scheduling/provider-schedules/{schedule_id}/generate-slots */
export function generateSlots(
  scheduleId: string,
  body: SlotGenerationRequest,
): Promise<SlotGenerationResult> {
  return post<SlotGenerationResult>(
    route`/scheduling/provider-schedules/${scheduleId}/generate-slots`,
    body,
  );
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useProviderAvailability(
  query: AvailabilityQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<AvailabilitySlot>> {
  return useQuery({
    queryKey: qk.scheduling.availabilityList(query),
    queryFn: ({ signal }) => fetchProviderAvailability(query, signal),
    enabled: options.enabled ?? true,
    // Slots are contended; a stale grid books a slot that is already gone.
    staleTime: options.staleTime ?? 10_000,
    refetchInterval: options.refetchInterval,
  });
}

export function useAppointments(
  query: AppointmentListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<AppointmentResponse>> {
  return useQuery({
    queryKey: qk.scheduling.appointmentList(query),
    queryFn: ({ signal }) => fetchAppointments(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
    refetchInterval: options.refetchInterval,
  });
}

export function useAppointment(
  appointmentId: string,
  options: QueryHookOptions = {},
): UseQueryResult<AppointmentResponse> {
  return useQuery({
    queryKey: qk.scheduling.appointment(appointmentId),
    queryFn: ({ signal }) => fetchAppointment(appointmentId, signal),
    enabled: (options.enabled ?? true) && Boolean(appointmentId),
    staleTime: options.staleTime,
  });
}

export function useProviderSchedules(
  query: ProviderScheduleListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ProviderScheduleResponse>> {
  return useQuery({
    queryKey: qk.scheduling.providerScheduleList(query),
    queryFn: ({ signal }) => fetchProviderSchedules(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useBookAppointment(): UseMutationResult<
  BookingResponse,
  Error,
  AppointmentCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AppointmentCreate) => bookAppointment(body),
    onSuccess: (booking) => {
      toast.success("Appointment booked", {
        description:
          booking.invoice.balance_cents > 0
            ? `${formatMoney(
                booking.invoice.balance_cents,
                booking.invoice.currency,
              )} due`
            : undefined,
      });
      // Booking consumes a slot, so the availability grid is now wrong.
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.availability(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.appointments(),
      });
      void queryClient.invalidateQueries({ queryKey: qk.operations.invoices() });
    },
    onError: (error) => toastApiError(error, "Could not book the appointment"),
  });
}

export interface CancelAppointmentVariables {
  appointmentId: string;
  body?: CancelRequest;
}

export function useCancelAppointment(): UseMutationResult<
  AppointmentResponse,
  Error,
  CancelAppointmentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, body }: CancelAppointmentVariables) =>
      cancelAppointment(appointmentId, body ?? {}),
    onSuccess: (appointment) => {
      toast.success("Appointment cancelled");
      // Cancelling releases the slot back into the grid.
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.availability(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.appointments(),
      });
      queryClient.setQueryData(
        qk.scheduling.appointment(appointment.id),
        appointment,
      );
      void queryClient.invalidateQueries({ queryKey: qk.operations.invoices() });
    },
    onError: (error) =>
      toastApiError(error, "Could not cancel the appointment"),
  });
}

export interface RescheduleAppointmentVariables {
  appointmentId: string;
  body: RescheduleRequest;
}

export function useRescheduleAppointment(): UseMutationResult<
  AppointmentResponse,
  Error,
  RescheduleAppointmentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, body }: RescheduleAppointmentVariables) =>
      rescheduleAppointment(appointmentId, body),
    onSuccess: (appointment) => {
      toast.success("Appointment rescheduled");
      // Two slots change: the released one and the newly taken one.
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.availability(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.appointments(),
      });
      queryClient.setQueryData(
        qk.scheduling.appointment(appointment.id),
        appointment,
      );
    },
    onError: (error) =>
      toastApiError(error, "Could not reschedule the appointment"),
  });
}

export interface PayAppointmentVariables {
  appointmentId: string;
  body?: SchedulingPaymentCreate;
}

export function usePayForAppointment(): UseMutationResult<
  PaymentResponse,
  Error,
  PayAppointmentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, body }: PayAppointmentVariables) =>
      payForAppointment(appointmentId, body ?? {}),
    onSuccess: (payment, variables) => {
      toast.success(
        `Paid ${formatMoney(payment.amount_cents, payment.currency)}`,
        { description: `Invoice ${payment.invoice.invoice_number}` },
      );
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.appointment(variables.appointmentId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.appointments(),
      });
      // Payment settles the invoice the booking raised.
      void queryClient.invalidateQueries({ queryKey: qk.operations.invoices() });
    },
    onError: (error) => toastApiError(error, "Payment failed"),
  });
}

export interface TelehealthSessionVariables {
  appointmentId: string;
  body?: TelehealthCreate;
}

export function useCreateTelehealthSession(): UseMutationResult<
  TelehealthSessionResponse,
  Error,
  TelehealthSessionVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ appointmentId, body }: TelehealthSessionVariables) =>
      createTelehealthSession(appointmentId, body ?? {}),
    onSuccess: (_session, variables) => {
      toast.success("Telehealth room ready");
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.appointment(variables.appointmentId),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not start the telehealth session"),
  });
}

export function useCreateProviderSchedule(): UseMutationResult<
  ProviderScheduleResponse,
  Error,
  ProviderScheduleCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProviderScheduleCreate) => createProviderSchedule(body),
    onSuccess: () => {
      toast.success("Schedule template saved");
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.providerSchedules(),
      });
    },
    onError: (error) => toastApiError(error, "Could not save the schedule"),
  });
}

export interface GenerateSlotsVariables {
  scheduleId: string;
  body: SlotGenerationRequest;
}

export function useGenerateSlots(): UseMutationResult<
  SlotGenerationResult,
  Error,
  GenerateSlotsVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ scheduleId, body }: GenerateSlotsVariables) =>
      generateSlots(scheduleId, body),
    onSuccess: (result) => {
      toast.success(`${result.created} slots published`, {
        description:
          result.skipped > 0 ? `${result.skipped} already existed` : undefined,
      });
      // New slots must appear in the booking grid immediately.
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.availability(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.scheduling.providerSchedules(),
      });
    },
    onError: (error) => toastApiError(error, "Could not publish slots"),
  });
}

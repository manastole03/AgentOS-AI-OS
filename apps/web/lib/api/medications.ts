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
  post,
  qk,
  route,
  toastApiError,
  type PageQuery,
  type QueryHookOptions,
} from "./client";
import type {
  AckResult,
  AdherenceReport,
  GenerateOccurrencesRequest,
  GenerationResult,
  MedicationStatementOut,
  MedicationStatementStatus,
  Page,
  PrescriptionCreate,
  PrescriptionOut,
  PrescriptionStatus,
  ReminderAck,
  ReminderOut,
  SafetyCheckBatch,
  SafetyCheckOut,
  ScheduleCreate,
  ScheduleOut,
} from "./types";

/**
 * Prescribing, dose scheduling, reminders and adherence.
 *
 * Backend router: `/api/v1/medications`.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

export type MedicationListQuery = PageQuery & {
  status?: MedicationStatementStatus | null;
};

export type PrescriptionListQuery = PageQuery & {
  status?: PrescriptionStatus | null;
  include_superseded?: boolean;
};

export type AdherenceQuery = {
  /** Trailing window in days; the backend caps this. */
  days?: number;
};

export type ReminderListQuery = PageQuery & {
  /** `upcoming`, `due` or `past` — the reminder window to project. */
  window?: string;
  days?: number;
};

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/medications/patients/{patient_id}/medications */
export function fetchMedications(
  patientId: string,
  query: MedicationListQuery = {},
  signal?: AbortSignal,
): Promise<Page<MedicationStatementOut>> {
  return get<Page<MedicationStatementOut>>(
    route`/medications/patients/${patientId}/medications`,
    { query, signal },
  );
}

/** GET /api/v1/medications/patients/{patient_id}/prescriptions */
export function fetchPrescriptions(
  patientId: string,
  query: PrescriptionListQuery = {},
  signal?: AbortSignal,
): Promise<Page<PrescriptionOut>> {
  return get<Page<PrescriptionOut>>(
    route`/medications/patients/${patientId}/prescriptions`,
    { query, signal },
  );
}

/** POST /api/v1/medications/patients/{patient_id}/prescriptions */
export function createPrescription(
  patientId: string,
  body: PrescriptionCreate,
): Promise<PrescriptionOut> {
  return post<PrescriptionOut>(
    route`/medications/patients/${patientId}/prescriptions`,
    body,
  );
}

/** GET /api/v1/medications/patients/{patient_id}/adherence */
export function fetchAdherence(
  patientId: string,
  query: AdherenceQuery = {},
  signal?: AbortSignal,
): Promise<AdherenceReport> {
  return get<AdherenceReport>(
    route`/medications/patients/${patientId}/adherence`,
    { query, signal },
  );
}

/** GET /api/v1/medications/patients/{patient_id}/reminders */
export function fetchReminders(
  patientId: string,
  query: ReminderListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ReminderOut>> {
  return get<Page<ReminderOut>>(
    route`/medications/patients/${patientId}/reminders`,
    { query, signal },
  );
}

/** POST /api/v1/medications/prescriptions/{prescription_id}/safety-checks */
export function runSafetyChecks(
  prescriptionId: string,
  body: SafetyCheckBatch,
): Promise<SafetyCheckOut[]> {
  return post<SafetyCheckOut[]>(
    route`/medications/prescriptions/${prescriptionId}/safety-checks`,
    body,
  );
}

/** POST /api/v1/medications/medication-requests/{medication_request_id}/schedule */
export function createMedicationSchedule(
  medicationRequestId: string,
  body: ScheduleCreate,
): Promise<ScheduleOut[]> {
  return post<ScheduleOut[]>(
    route`/medications/medication-requests/${medicationRequestId}/schedule`,
    body,
  );
}

/** POST /api/v1/medications/schedules/{schedule_id}/generate-occurrences */
export function generateOccurrences(
  scheduleId: string,
  body: GenerateOccurrencesRequest = {},
): Promise<GenerationResult> {
  return post<GenerationResult>(
    route`/medications/schedules/${scheduleId}/generate-occurrences`,
    body,
  );
}

/** POST /api/v1/medications/reminders/{occurrence_id}/ack */
export function acknowledgeReminder(
  occurrenceId: string,
  body: ReminderAck,
): Promise<AckResult> {
  return post<AckResult>(
    route`/medications/reminders/${occurrenceId}/ack`,
    body,
  );
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useMedications(
  patientId: string,
  query: MedicationListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<MedicationStatementOut>> {
  return useQuery({
    queryKey: qk.medications.statementList(patientId, query),
    queryFn: ({ signal }) => fetchMedications(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function usePrescriptions(
  patientId: string,
  query: PrescriptionListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<PrescriptionOut>> {
  return useQuery({
    queryKey: qk.medications.prescriptionList(patientId, query),
    queryFn: ({ signal }) => fetchPrescriptions(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useAdherence(
  patientId: string,
  query: AdherenceQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<AdherenceReport> {
  return useQuery({
    queryKey: qk.medications.adherenceReport(patientId, query),
    queryFn: ({ signal }) => fetchAdherence(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useReminders(
  patientId: string,
  query: ReminderListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ReminderOut>> {
  return useQuery({
    queryKey: qk.medications.reminderList(patientId, query),
    queryFn: ({ signal }) => fetchReminders(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
    refetchInterval: options.refetchInterval,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreatePrescription(
  patientId: string,
): UseMutationResult<PrescriptionOut, Error, PrescriptionCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PrescriptionCreate) =>
      createPrescription(patientId, body),
    onSuccess: (prescription) => {
      const alerts = (prescription.safety_checks ?? []).filter(
        (check) => check.outcome === "alerted",
      );
      if (alerts.length > 0) {
        toast.warning(
          `Prescription written with ${alerts.length} safety alert${
            alerts.length === 1 ? "" : "s"
          }`,
          { description: alerts[0].message },
        );
      } else {
        toast.success("Prescription written", {
          description: prescription.prescription_number,
        });
      }
      void queryClient.invalidateQueries({
        queryKey: qk.medications.prescriptions(patientId),
      });
      // A new script changes the active medication list and the dose plan.
      void queryClient.invalidateQueries({
        queryKey: qk.medications.statements(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.summary(patientId),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not write the prescription"),
  });
}

export interface RunSafetyChecksVariables {
  prescriptionId: string;
  body: SafetyCheckBatch;
  /** Refreshes the prescription list once the checks are stored. */
  patientId?: string;
}

export function useRunSafetyChecks(): UseMutationResult<
  SafetyCheckOut[],
  Error,
  RunSafetyChecksVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ prescriptionId, body }: RunSafetyChecksVariables) =>
      runSafetyChecks(prescriptionId, body),
    onSuccess: (checks, variables) => {
      const alerts = checks.filter((check) => check.outcome === "alerted");
      if (alerts.length > 0) {
        toast.warning(
          `${alerts.length} safety alert${alerts.length === 1 ? "" : "s"}`,
          { description: alerts[0].message },
        );
      } else {
        toast.success("No safety alerts");
      }
      if (variables.patientId) {
        void queryClient.invalidateQueries({
          queryKey: qk.medications.prescriptions(variables.patientId),
        });
      }
    },
    onError: (error) => toastApiError(error, "Could not run the safety checks"),
  });
}

export interface CreateScheduleVariables {
  medicationRequestId: string;
  body: ScheduleCreate;
  /** Refreshes the reminder feed for the patient the schedule belongs to. */
  patientId?: string;
}

export function useCreateMedicationSchedule(): UseMutationResult<
  ScheduleOut[],
  Error,
  CreateScheduleVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ medicationRequestId, body }: CreateScheduleVariables) =>
      createMedicationSchedule(medicationRequestId, body),
    onSuccess: (schedules, variables) => {
      toast.success(
        `Dose schedule created (${schedules.length} time${
          schedules.length === 1 ? "" : "s"
        } a day)`,
      );
      const patientId = variables.patientId ?? schedules[0]?.patient_user_id;
      if (patientId) {
        void queryClient.invalidateQueries({
          queryKey: qk.medications.patient(patientId),
        });
      }
    },
    onError: (error) => toastApiError(error, "Could not create the schedule"),
  });
}

export interface GenerateOccurrencesVariables {
  scheduleId: string;
  body?: GenerateOccurrencesRequest;
  /** Refreshes the reminder feed once occurrences are materialised. */
  patientId?: string;
}

export function useGenerateOccurrences(): UseMutationResult<
  GenerationResult,
  Error,
  GenerateOccurrencesVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ scheduleId, body }: GenerateOccurrencesVariables) =>
      generateOccurrences(scheduleId, body ?? {}),
    onSuccess: (result, variables) => {
      toast.success(`${result.created} reminders scheduled`, {
        description: result.course_complete
          ? "Course complete"
          : `${result.skipped} already existed`,
      });
      if (variables.patientId) {
        void queryClient.invalidateQueries({
          queryKey: qk.medications.reminders(variables.patientId),
        });
      }
    },
    onError: (error) => toastApiError(error, "Could not generate reminders"),
  });
}

export interface AcknowledgeReminderVariables {
  occurrenceId: string;
  body: ReminderAck;
  /** Refreshes the reminder feed and the adherence report. */
  patientId?: string;
}

export function useAcknowledgeReminder(): UseMutationResult<
  AckResult,
  Error,
  AcknowledgeReminderVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ occurrenceId, body }: AcknowledgeReminderVariables) =>
      acknowledgeReminder(occurrenceId, body),
    onSuccess: (result, variables) => {
      toast.success(
        result.event.status === "taken" ? "Dose logged" : "Dose updated",
      );
      const patientId = variables.patientId ?? result.event.patient_user_id;
      void queryClient.invalidateQueries({
        queryKey: qk.medications.reminders(patientId),
      });
      // Logging a dose moves the adherence numerator.
      void queryClient.invalidateQueries({
        queryKey: qk.medications.adherence(patientId),
      });
    },
    onError: (error) => toastApiError(error, "Could not log the dose"),
  });
}

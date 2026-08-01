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
  patch,
  post,
  qk,
  route,
  toastApiError,
  type PageQuery,
  type QueryHookOptions,
} from "./client";
import type {
  AllergyCreate,
  AllergyOut,
  AllergyReviewIn,
  AllergyStatusOut,
  CertificateIssueIn,
  CertificateOut,
  ClinicalStatus,
  ConditionCreate,
  ConditionOut,
  EncounterClass,
  EncounterCreate,
  EncounterOut,
  EncounterStatus,
  GrowthCreate,
  GrowthOut,
  GrowthPercentileSeries,
  GrowthSource,
  ImmunizationCreate,
  ImmunizationDueOut,
  ImmunizationOut,
  Page,
  PatientSummary,
  StatusChange,
  TimelineEntry,
  VitalCreate,
  VitalOut,
} from "./types";

/**
 * Longitudinal patient record: summary, timeline, allergies, conditions,
 * encounters, vitals, growth and immunizations.
 *
 * Backend router: `/api/v1/clinical`.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

export type AllergyListQuery = PageQuery & {
  active_only?: boolean;
};

export type ConditionListQuery = PageQuery & {
  clinical_status?: ClinicalStatus | null;
  include_superseded?: boolean;
};

export type EncounterListQuery = PageQuery & {
  status?: EncounterStatus | null;
  class_code?: EncounterClass | null;
  /** ISO-8601 lower bound on `started_at`. */
  since?: string | null;
};

export type VitalListQuery = PageQuery & {
  /** LOINC code, e.g. `8867-4` for heart rate. */
  code?: string | null;
  since?: string | null;
};

export type GrowthListQuery = PageQuery & {
  since?: string | null;
};

export type GrowthPercentileQuery = PageQuery & {
  standard?: GrowthSource;
  since?: string | null;
};

export type ImmunizationListQuery = PageQuery & {
  vaccine_code?: string | null;
};

export type ImmunizationDueQuery = {
  horizon_days?: number;
};

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/clinical/patients/{patient_id}/summary */
export function fetchPatientSummary(
  patientId: string,
  signal?: AbortSignal,
): Promise<PatientSummary> {
  return get<PatientSummary>(route`/clinical/patients/${patientId}/summary`, {
    signal,
  });
}

/** GET /api/v1/clinical/patients/{patient_id}/timeline */
export function fetchPatientTimeline(
  patientId: string,
  query: PageQuery = {},
  signal?: AbortSignal,
): Promise<Page<TimelineEntry>> {
  return get<Page<TimelineEntry>>(
    route`/clinical/patients/${patientId}/timeline`,
    { query, signal },
  );
}

/** GET /api/v1/clinical/patients/{patient_id}/allergies */
export function fetchAllergies(
  patientId: string,
  query: AllergyListQuery = {},
  signal?: AbortSignal,
): Promise<Page<AllergyOut>> {
  return get<Page<AllergyOut>>(
    route`/clinical/patients/${patientId}/allergies`,
    { query, signal },
  );
}

/** POST /api/v1/clinical/patients/{patient_id}/allergies */
export function createAllergy(
  patientId: string,
  body: AllergyCreate,
): Promise<AllergyOut> {
  return post<AllergyOut>(
    route`/clinical/patients/${patientId}/allergies`,
    body,
  );
}

/** POST /api/v1/clinical/patients/{patient_id}/allergies/review */
export function reviewAllergies(
  patientId: string,
  body: AllergyReviewIn,
): Promise<AllergyStatusOut> {
  return post<AllergyStatusOut>(
    route`/clinical/patients/${patientId}/allergies/review`,
    body,
  );
}

/** GET /api/v1/clinical/patients/{patient_id}/conditions */
export function fetchConditions(
  patientId: string,
  query: ConditionListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ConditionOut>> {
  return get<Page<ConditionOut>>(
    route`/clinical/patients/${patientId}/conditions`,
    { query, signal },
  );
}

/** POST /api/v1/clinical/patients/{patient_id}/conditions */
export function createCondition(
  patientId: string,
  body: ConditionCreate,
): Promise<ConditionOut> {
  return post<ConditionOut>(
    route`/clinical/patients/${patientId}/conditions`,
    body,
  );
}

/** GET /api/v1/clinical/patients/{patient_id}/encounters */
export function fetchEncounters(
  patientId: string,
  query: EncounterListQuery = {},
  signal?: AbortSignal,
): Promise<Page<EncounterOut>> {
  return get<Page<EncounterOut>>(
    route`/clinical/patients/${patientId}/encounters`,
    { query, signal },
  );
}

/** POST /api/v1/clinical/patients/{patient_id}/encounters */
export function createEncounter(
  patientId: string,
  body: EncounterCreate,
): Promise<EncounterOut> {
  return post<EncounterOut>(
    route`/clinical/patients/${patientId}/encounters`,
    body,
  );
}

/** PATCH /api/v1/clinical/encounters/{encounter_id} */
export function changeEncounterStatus(
  encounterId: string,
  body: StatusChange,
): Promise<EncounterOut> {
  return patch<EncounterOut>(route`/clinical/encounters/${encounterId}`, body);
}

/** GET /api/v1/clinical/patients/{patient_id}/vitals */
export function fetchVitals(
  patientId: string,
  query: VitalListQuery = {},
  signal?: AbortSignal,
): Promise<Page<VitalOut>> {
  return get<Page<VitalOut>>(route`/clinical/patients/${patientId}/vitals`, {
    query,
    signal,
  });
}

/** POST /api/v1/clinical/patients/{patient_id}/vitals */
export function createVital(
  patientId: string,
  body: VitalCreate,
): Promise<VitalOut> {
  return post<VitalOut>(route`/clinical/patients/${patientId}/vitals`, body);
}

/** GET /api/v1/clinical/patients/{patient_id}/growth */
export function fetchGrowth(
  patientId: string,
  query: GrowthListQuery = {},
  signal?: AbortSignal,
): Promise<Page<GrowthOut>> {
  return get<Page<GrowthOut>>(route`/clinical/patients/${patientId}/growth`, {
    query,
    signal,
  });
}

/** POST /api/v1/clinical/patients/{patient_id}/growth */
export function createGrowthMeasurement(
  patientId: string,
  body: GrowthCreate,
  standard?: GrowthSource,
): Promise<GrowthOut> {
  return post<GrowthOut>(route`/clinical/patients/${patientId}/growth`, body, {
    query: { standard },
  });
}

/** GET /api/v1/clinical/patients/{patient_id}/growth/percentiles */
export function fetchGrowthPercentiles(
  patientId: string,
  query: GrowthPercentileQuery = {},
  signal?: AbortSignal,
): Promise<GrowthPercentileSeries> {
  return get<GrowthPercentileSeries>(
    route`/clinical/patients/${patientId}/growth/percentiles`,
    { query, signal },
  );
}

/** GET /api/v1/clinical/patients/{patient_id}/immunizations */
export function fetchImmunizations(
  patientId: string,
  query: ImmunizationListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ImmunizationOut>> {
  return get<Page<ImmunizationOut>>(
    route`/clinical/patients/${patientId}/immunizations`,
    { query, signal },
  );
}

/** POST /api/v1/clinical/patients/{patient_id}/immunizations */
export function createImmunization(
  patientId: string,
  body: ImmunizationCreate,
): Promise<ImmunizationOut> {
  return post<ImmunizationOut>(
    route`/clinical/patients/${patientId}/immunizations`,
    body,
  );
}

/** GET /api/v1/clinical/patients/{patient_id}/immunizations/due */
export function fetchImmunizationsDue(
  patientId: string,
  query: ImmunizationDueQuery = {},
  signal?: AbortSignal,
): Promise<ImmunizationDueOut> {
  return get<ImmunizationDueOut>(
    route`/clinical/patients/${patientId}/immunizations/due`,
    { query, signal },
  );
}

/** GET /api/v1/clinical/immunizations/{immunization_id}/certificate */
export function fetchImmunizationCertificate(
  immunizationId: string,
  signal?: AbortSignal,
): Promise<CertificateOut> {
  return get<CertificateOut>(
    route`/clinical/immunizations/${immunizationId}/certificate`,
    { signal },
  );
}

/** POST /api/v1/clinical/immunizations/{immunization_id}/certificate */
export function issueImmunizationCertificate(
  immunizationId: string,
  body: CertificateIssueIn = {},
): Promise<CertificateOut> {
  return post<CertificateOut>(
    route`/clinical/immunizations/${immunizationId}/certificate`,
    body,
  );
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function usePatientSummary(
  patientId: string,
  options: QueryHookOptions = {},
): UseQueryResult<PatientSummary> {
  return useQuery({
    queryKey: qk.clinical.summary(patientId),
    queryFn: ({ signal }) => fetchPatientSummary(patientId, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
    refetchInterval: options.refetchInterval,
  });
}

export function usePatientTimeline(
  patientId: string,
  query: PageQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<TimelineEntry>> {
  return useQuery({
    queryKey: qk.clinical.timelineList(patientId, query),
    queryFn: ({ signal }) => fetchPatientTimeline(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useAllergies(
  patientId: string,
  query: AllergyListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<AllergyOut>> {
  return useQuery({
    queryKey: qk.clinical.allergyList(patientId, query),
    queryFn: ({ signal }) => fetchAllergies(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useConditions(
  patientId: string,
  query: ConditionListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ConditionOut>> {
  return useQuery({
    queryKey: qk.clinical.conditionList(patientId, query),
    queryFn: ({ signal }) => fetchConditions(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useEncounters(
  patientId: string,
  query: EncounterListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<EncounterOut>> {
  return useQuery({
    queryKey: qk.clinical.encounterList(patientId, query),
    queryFn: ({ signal }) => fetchEncounters(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useVitals(
  patientId: string,
  query: VitalListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<VitalOut>> {
  return useQuery({
    queryKey: qk.clinical.vitalList(patientId, query),
    queryFn: ({ signal }) => fetchVitals(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useGrowth(
  patientId: string,
  query: GrowthListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<GrowthOut>> {
  return useQuery({
    queryKey: qk.clinical.growthList(patientId, query),
    queryFn: ({ signal }) => fetchGrowth(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useGrowthPercentiles(
  patientId: string,
  query: GrowthPercentileQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<GrowthPercentileSeries> {
  return useQuery({
    queryKey: qk.clinical.growthPercentiles(patientId, query),
    queryFn: ({ signal }) => fetchGrowthPercentiles(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useImmunizations(
  patientId: string,
  query: ImmunizationListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ImmunizationOut>> {
  return useQuery({
    queryKey: qk.clinical.immunizationList(patientId, query),
    queryFn: ({ signal }) => fetchImmunizations(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useImmunizationsDue(
  patientId: string,
  query: ImmunizationDueQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<ImmunizationDueOut> {
  return useQuery({
    queryKey: qk.clinical.immunizationsDue(patientId, query),
    queryFn: ({ signal }) => fetchImmunizationsDue(patientId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(patientId),
    staleTime: options.staleTime,
  });
}

export function useImmunizationCertificate(
  immunizationId: string,
  options: QueryHookOptions = {},
): UseQueryResult<CertificateOut> {
  return useQuery({
    queryKey: qk.clinical.certificate(immunizationId),
    queryFn: ({ signal }) =>
      fetchImmunizationCertificate(immunizationId, signal),
    enabled: (options.enabled ?? true) && Boolean(immunizationId),
    staleTime: options.staleTime,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreateAllergy(
  patientId: string,
): UseMutationResult<AllergyOut, Error, AllergyCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AllergyCreate) => createAllergy(patientId, body),
    onSuccess: (allergy) => {
      toast.success("Allergy recorded", {
        description: allergy.substance_display,
      });
      // The summary carries active allergies and the allergy banner.
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.allergies(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.summary(patientId),
      });
    },
    onError: (error) => toastApiError(error, "Could not record the allergy"),
  });
}

export function useReviewAllergies(
  patientId: string,
): UseMutationResult<AllergyStatusOut, Error, AllergyReviewIn> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AllergyReviewIn) => reviewAllergies(patientId, body),
    onSuccess: (status) => {
      toast.success(
        status.no_known_allergies
          ? "Marked as no known allergies"
          : "Allergy list reviewed",
      );
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.allergies(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.summary(patientId),
      });
    },
    onError: (error) => toastApiError(error, "Could not save the review"),
  });
}

export function useCreateCondition(
  patientId: string,
): UseMutationResult<ConditionOut, Error, ConditionCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ConditionCreate) => createCondition(patientId, body),
    onSuccess: (condition) => {
      toast.success("Condition added", {
        description: condition.condition_display,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.conditions(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.summary(patientId),
      });
    },
    onError: (error) => toastApiError(error, "Could not add the condition"),
  });
}

export function useCreateEncounter(
  patientId: string,
): UseMutationResult<EncounterOut, Error, EncounterCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: EncounterCreate) => createEncounter(patientId, body),
    onSuccess: () => {
      toast.success("Encounter opened");
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.encounters(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.timeline(patientId),
      });
    },
    onError: (error) => toastApiError(error, "Could not open the encounter"),
  });
}

export interface ChangeEncounterStatusVariables {
  encounterId: string;
  body: StatusChange;
}

export function useChangeEncounterStatus(): UseMutationResult<
  EncounterOut,
  Error,
  ChangeEncounterStatusVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ encounterId, body }: ChangeEncounterStatusVariables) =>
      changeEncounterStatus(encounterId, body),
    onSuccess: (encounter) => {
      toast.success(`Encounter marked ${encounter.status}`);
      // The response carries the patient, so both lists can be targeted.
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.encounters(encounter.patient_user_id),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.timeline(encounter.patient_user_id),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.encounter(encounter.id),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not change the encounter status"),
  });
}

export function useCreateVital(
  patientId: string,
): UseMutationResult<VitalOut, Error, VitalCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: VitalCreate) => createVital(patientId, body),
    onSuccess: () => {
      toast.success("Vitals recorded");
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.vitals(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.summary(patientId),
      });
    },
    onError: (error) => toastApiError(error, "Could not record the vitals"),
  });
}

export interface CreateGrowthVariables {
  body: GrowthCreate;
  standard?: GrowthSource;
}

export function useCreateGrowthMeasurement(
  patientId: string,
): UseMutationResult<GrowthOut, Error, CreateGrowthVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ body, standard }: CreateGrowthVariables) =>
      createGrowthMeasurement(patientId, body, standard),
    onSuccess: () => {
      toast.success("Growth measurement recorded");
      // Percentiles are rescored server-side, so the chart series must refetch.
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.growth(patientId),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not record the measurement"),
  });
}

export function useCreateImmunization(
  patientId: string,
): UseMutationResult<ImmunizationOut, Error, ImmunizationCreate> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ImmunizationCreate) => createImmunization(patientId, body),
    onSuccess: (immunization) => {
      toast.success("Immunization recorded", {
        description: immunization.vaccine_display,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.immunizations(patientId),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.summary(patientId),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not record the immunization"),
  });
}

export interface IssueCertificateVariables {
  immunizationId: string;
  body?: CertificateIssueIn;
  /** Invalidates the patient's immunization list once the certificate exists. */
  patientId?: string;
}

export function useIssueImmunizationCertificate(): UseMutationResult<
  CertificateOut,
  Error,
  IssueCertificateVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ immunizationId, body }: IssueCertificateVariables) =>
      issueImmunizationCertificate(immunizationId, body ?? {}),
    onSuccess: (certificate, variables) => {
      toast.success("Certificate issued", {
        description: certificate.certificate_number,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.clinical.certificate(variables.immunizationId),
      });
      if (variables.patientId) {
        void queryClient.invalidateQueries({
          queryKey: qk.clinical.immunizations(variables.patientId),
        });
      }
    },
    onError: (error) => toastApiError(error, "Could not issue the certificate"),
  });
}

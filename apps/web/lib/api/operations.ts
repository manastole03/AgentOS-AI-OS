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
  patch,
  post,
  qk,
  route,
  toastApiError,
  type PageQuery,
  type QueryHookOptions,
} from "./client";
import { formatMoney } from "./format";
import type {
  AddendumCreate,
  AddendumOut,
  BreakGlassEntry,
  ClinicalNoteCreate,
  ClinicalNoteOut,
  CodeType,
  DataSubjectRequestOut,
  DepartmentCreate,
  DepartmentOut,
  DepartmentUpdate,
  DsrStatus,
  DsrType,
  EncounterCodeCreate,
  EncounterCodeOut,
  InvoiceDetailOut,
  InvoiceStatus,
  NoteSignRequest,
  OperationsInvoiceOut,
  OperationsPaymentCreate,
  Page,
  PaymentResult,
  PhiAccessOut,
  PlatformAnalytics,
  PractitionerRoleCreate,
  PractitionerRoleOut,
  PractitionerRoleUpdate,
  ReferralCreate,
  ReferralOut,
  ReferralStatus,
  ReferralStatusChange,
  RefundCreate,
  RefundResult,
  ReviewStatus,
  RevenueCycleSummary,
  ServiceItemCreate,
  ServiceItemOut,
  ServiceItemUpdate,
  SupportCaseOut,
  SupportSeverity,
  SupportStatus,
} from "./types";

/**
 * Facility operations, clinical documentation and platform governance.
 *
 * Backend router: `/api/v1/operations`. The routes are gated per segment:
 * departments / practitioners / catalog / invoices belong to the hospital
 * role, notes / codes / referrals to clinicians, and support cases, PHI access
 * and data-subject requests to platform admins.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

/** Mirrors `healthos_api.domain.operations.CredentialingStatus`. */
export type CredentialingStatus =
  | "pending"
  | "active"
  | "suspended"
  | "expired"
  | "revoked";

export type { ReviewStatus };

export type DepartmentListQuery = PageQuery & {
  is_active?: boolean | null;
  search?: string | null;
};

export type PractitionerListQuery = PageQuery & {
  credentialing_status?: CredentialingStatus | null;
  expiring_within_days?: number | null;
  department_id?: string | null;
  specialty_code?: string | null;
  is_active?: boolean | null;
};

export type ServiceCatalogQuery = PageQuery & {
  service_code?: string | null;
  department_id?: string | null;
  effective_on?: string | null;
  is_active?: boolean | null;
  search?: string | null;
};

export type InvoiceListQuery = PageQuery & {
  status?: InvoiceStatus | null;
  /** Issued-on-or-after, ISO-8601 date-time. */
  from?: string | null;
  /** Issued-on-or-before, ISO-8601 date-time. */
  to?: string | null;
  patient_id?: string | null;
};

export type RevenueCycleQuery = {
  from?: string | null;
  to?: string | null;
  currency?: string | null;
};

export type EncounterNoteQuery = PageQuery & {
  /** Amended notes keep their superseded predecessor; opt in to see it. */
  include_superseded?: boolean;
};

export type EncounterCodeQuery = PageQuery & {
  code_type?: CodeType | null;
  review_status?: ReviewStatus | null;
};

export type ReferralListQuery = PageQuery & {
  status?: ReferralStatus | null;
  patient_id?: string | null;
  specialty_code?: string | null;
  direction?: "incoming" | "outgoing" | null;
};

export type SupportCaseListQuery = PageQuery & {
  status?: SupportStatus | null;
  severity?: SupportSeverity | null;
  queue?: string | null;
  assignee_user_id?: string | null;
  breached_only?: boolean | null;
};

export type PhiAccessListQuery = PageQuery & {
  patient_id?: string | null;
  actor_id?: string | null;
  from?: string | null;
  to?: string | null;
  purpose_of_use?: string | null;
  resource_type?: string | null;
};

export type BreakGlassQuery = PageQuery & {
  from?: string | null;
  to?: string | null;
  actor_id?: string | null;
};

export type DataSubjectRequestListQuery = PageQuery & {
  status?: DsrStatus | null;
  request_type?: DsrType | null;
  subject_id?: string | null;
  overdue_only?: boolean | null;
};

export type PlatformAnalyticsQuery = {
  from?: string | null;
  to?: string | null;
};

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/operations/departments */
export function fetchDepartments(
  query: DepartmentListQuery = {},
  signal?: AbortSignal,
): Promise<Page<DepartmentOut>> {
  return get<Page<DepartmentOut>>("/operations/departments", { query, signal });
}

/** GET /api/v1/operations/practitioners */
export function fetchPractitioners(
  query: PractitionerListQuery = {},
  signal?: AbortSignal,
): Promise<Page<PractitionerRoleOut>> {
  return get<Page<PractitionerRoleOut>>("/operations/practitioners", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/service-catalog */
export function fetchServiceCatalog(
  query: ServiceCatalogQuery = {},
  signal?: AbortSignal,
): Promise<Page<ServiceItemOut>> {
  return get<Page<ServiceItemOut>>("/operations/service-catalog", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/invoices */
export function fetchInvoices(
  query: InvoiceListQuery = {},
  signal?: AbortSignal,
): Promise<Page<OperationsInvoiceOut>> {
  return get<Page<OperationsInvoiceOut>>("/operations/invoices", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/invoices/{invoice_id} */
export function fetchInvoice(
  invoiceId: string,
  signal?: AbortSignal,
): Promise<InvoiceDetailOut> {
  return get<InvoiceDetailOut>(route`/operations/invoices/${invoiceId}`, {
    signal,
  });
}

/** GET /api/v1/operations/revenue-cycle/summary */
export function fetchRevenueCycleSummary(
  query: RevenueCycleQuery = {},
  signal?: AbortSignal,
): Promise<RevenueCycleSummary> {
  return get<RevenueCycleSummary>("/operations/revenue-cycle/summary", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/referrals */
export function fetchReferrals(
  query: ReferralListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ReferralOut>> {
  return get<Page<ReferralOut>>("/operations/referrals", { query, signal });
}

/** GET /api/v1/operations/support-cases */
export function fetchSupportCases(
  query: SupportCaseListQuery = {},
  signal?: AbortSignal,
): Promise<Page<SupportCaseOut>> {
  return get<Page<SupportCaseOut>>("/operations/support-cases", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/phi-access */
export function fetchPhiAccess(
  query: PhiAccessListQuery = {},
  signal?: AbortSignal,
): Promise<Page<PhiAccessOut>> {
  return get<Page<PhiAccessOut>>("/operations/phi-access", { query, signal });
}

/** GET /api/v1/operations/phi-access/break-glass */
export function fetchBreakGlass(
  query: BreakGlassQuery = {},
  signal?: AbortSignal,
): Promise<Page<BreakGlassEntry>> {
  return get<Page<BreakGlassEntry>>("/operations/phi-access/break-glass", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/data-subject-requests */
export function fetchDataSubjectRequests(
  query: DataSubjectRequestListQuery = {},
  signal?: AbortSignal,
): Promise<Page<DataSubjectRequestOut>> {
  return get<Page<DataSubjectRequestOut>>("/operations/data-subject-requests", {
    query,
    signal,
  });
}

/** GET /api/v1/operations/analytics/platform */
export function fetchPlatformAnalytics(
  query: PlatformAnalyticsQuery = {},
  signal?: AbortSignal,
): Promise<PlatformAnalytics> {
  return get<PlatformAnalytics>("/operations/analytics/platform", {
    query,
    signal,
  });
}

/** POST /api/v1/operations/departments */
export function createDepartment(body: DepartmentCreate): Promise<DepartmentOut> {
  return post<DepartmentOut>("/operations/departments", body);
}

/** PATCH /api/v1/operations/departments/{department_id} */
export function updateDepartment(
  departmentId: string,
  body: DepartmentUpdate,
): Promise<DepartmentOut> {
  return patch<DepartmentOut>(
    route`/operations/departments/${departmentId}`,
    body,
  );
}

/** POST /api/v1/operations/practitioners */
export function createPractitionerRole(
  body: PractitionerRoleCreate,
): Promise<PractitionerRoleOut> {
  return post<PractitionerRoleOut>("/operations/practitioners", body);
}

/** PATCH /api/v1/operations/practitioners/{role_id} */
export function updatePractitionerRole(
  roleId: string,
  body: PractitionerRoleUpdate,
): Promise<PractitionerRoleOut> {
  return patch<PractitionerRoleOut>(
    route`/operations/practitioners/${roleId}`,
    body,
  );
}

/** POST /api/v1/operations/service-catalog */
export function createServiceItem(
  body: ServiceItemCreate,
): Promise<ServiceItemOut> {
  return post<ServiceItemOut>("/operations/service-catalog", body);
}

/** PATCH /api/v1/operations/service-catalog/{service_item_id} */
export function updateServiceItem(
  serviceItemId: string,
  body: ServiceItemUpdate,
): Promise<ServiceItemOut> {
  return patch<ServiceItemOut>(
    route`/operations/service-catalog/${serviceItemId}`,
    body,
  );
}

/**
 * POST /api/v1/operations/invoices/{invoice_id}/payments
 *
 * The ledger keys the attempt on `idempotency_key`, so a retry replays the
 * stored capture instead of taking the money twice.
 */
export function recordInvoicePayment(
  invoiceId: string,
  body: OperationsPaymentCreate,
): Promise<PaymentResult> {
  return post<PaymentResult>(
    route`/operations/invoices/${invoiceId}/payments`,
    body,
    { idempotencyKey: body.idempotency_key },
  );
}

/** POST /api/v1/operations/payments/{payment_id}/refund */
export function refundPayment(
  paymentId: string,
  body: RefundCreate,
): Promise<RefundResult> {
  return post<RefundResult>(
    route`/operations/payments/${paymentId}/refund`,
    body,
  );
}

/** GET /api/v1/operations/encounters/{encounter_id}/notes */
export function fetchEncounterNotes(
  encounterId: string,
  query: EncounterNoteQuery = {},
  signal?: AbortSignal,
): Promise<Page<ClinicalNoteOut>> {
  return get<Page<ClinicalNoteOut>>(
    route`/operations/encounters/${encounterId}/notes`,
    { query, signal },
  );
}

/** POST /api/v1/operations/encounters/{encounter_id}/notes */
export function createEncounterNote(
  encounterId: string,
  body: ClinicalNoteCreate,
): Promise<ClinicalNoteOut> {
  return post<ClinicalNoteOut>(
    route`/operations/encounters/${encounterId}/notes`,
    body,
  );
}

/**
 * POST /api/v1/operations/notes/{note_id}/sign
 *
 * Signing makes the row immutable — a database trigger rejects any later
 * update. After this call the note can only grow an addendum.
 */
export function signNote(
  noteId: string,
  body: NoteSignRequest = {},
): Promise<ClinicalNoteOut> {
  return post<ClinicalNoteOut>(route`/operations/notes/${noteId}/sign`, body);
}

/** POST /api/v1/operations/notes/{note_id}/addenda */
export function addNoteAddendum(
  noteId: string,
  body: AddendumCreate,
): Promise<AddendumOut> {
  return post<AddendumOut>(route`/operations/notes/${noteId}/addenda`, body);
}

/** GET /api/v1/operations/encounters/{encounter_id}/codes */
export function fetchEncounterCodes(
  encounterId: string,
  query: EncounterCodeQuery = {},
  signal?: AbortSignal,
): Promise<Page<EncounterCodeOut>> {
  return get<Page<EncounterCodeOut>>(
    route`/operations/encounters/${encounterId}/codes`,
    { query, signal },
  );
}

/** POST /api/v1/operations/encounters/{encounter_id}/codes */
export function createEncounterCode(
  encounterId: string,
  body: EncounterCodeCreate,
): Promise<EncounterCodeOut> {
  return post<EncounterCodeOut>(
    route`/operations/encounters/${encounterId}/codes`,
    body,
  );
}

/** POST /api/v1/operations/referrals */
export function createReferral(body: ReferralCreate): Promise<ReferralOut> {
  return post<ReferralOut>("/operations/referrals", body);
}

/** POST /api/v1/operations/referrals/{referral_id}/status */
export function changeReferralStatus(
  referralId: string,
  body: ReferralStatusChange,
): Promise<ReferralOut> {
  return post<ReferralOut>(
    route`/operations/referrals/${referralId}/status`,
    body,
  );
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useDepartments(
  query: DepartmentListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<DepartmentOut>> {
  return useQuery({
    queryKey: qk.operations.departmentList(query),
    queryFn: ({ signal }) => fetchDepartments(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function usePractitioners(
  query: PractitionerListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<PractitionerRoleOut>> {
  return useQuery({
    queryKey: qk.operations.practitionerList(query),
    queryFn: ({ signal }) => fetchPractitioners(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useServiceCatalog(
  query: ServiceCatalogQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ServiceItemOut>> {
  return useQuery({
    queryKey: qk.operations.serviceCatalogList(query),
    queryFn: ({ signal }) => fetchServiceCatalog(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useInvoices(
  query: InvoiceListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<OperationsInvoiceOut>> {
  return useQuery({
    queryKey: qk.operations.invoiceList(query),
    queryFn: ({ signal }) => fetchInvoices(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useInvoice(
  invoiceId: string,
  options: QueryHookOptions = {},
): UseQueryResult<InvoiceDetailOut> {
  return useQuery({
    queryKey: qk.operations.invoice(invoiceId),
    queryFn: ({ signal }) => fetchInvoice(invoiceId, signal),
    enabled: (options.enabled ?? true) && Boolean(invoiceId),
    staleTime: options.staleTime,
  });
}

export function useRevenueCycleSummary(
  query: RevenueCycleQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<RevenueCycleSummary> {
  return useQuery({
    queryKey: qk.operations.revenueCycle(query),
    queryFn: ({ signal }) => fetchRevenueCycleSummary(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useReferrals(
  query: ReferralListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ReferralOut>> {
  return useQuery({
    queryKey: qk.operations.referralList(query),
    queryFn: ({ signal }) => fetchReferrals(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useSupportCases(
  query: SupportCaseListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<SupportCaseOut>> {
  return useQuery({
    queryKey: qk.operations.supportCaseList(query),
    queryFn: ({ signal }) => fetchSupportCases(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function usePhiAccess(
  query: PhiAccessListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<PhiAccessOut>> {
  return useQuery({
    queryKey: qk.operations.phiAccessList(query),
    queryFn: ({ signal }) => fetchPhiAccess(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useBreakGlass(
  query: BreakGlassQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<BreakGlassEntry>> {
  return useQuery({
    queryKey: qk.operations.breakGlass(query),
    queryFn: ({ signal }) => fetchBreakGlass(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useDataSubjectRequests(
  query: DataSubjectRequestListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<DataSubjectRequestOut>> {
  return useQuery({
    queryKey: qk.operations.dataSubjectRequestList(query),
    queryFn: ({ signal }) => fetchDataSubjectRequests(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function usePlatformAnalytics(
  query: PlatformAnalyticsQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<PlatformAnalytics> {
  return useQuery({
    queryKey: qk.operations.platformAnalytics(query),
    queryFn: ({ signal }) => fetchPlatformAnalytics(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useEncounterNotes(
  encounterId: string,
  query: EncounterNoteQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ClinicalNoteOut>> {
  return useQuery({
    queryKey: qk.operations.encounterNoteList(encounterId, query),
    queryFn: ({ signal }) => fetchEncounterNotes(encounterId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(encounterId),
    staleTime: options.staleTime,
  });
}

export function useEncounterCodes(
  encounterId: string,
  query: EncounterCodeQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<EncounterCodeOut>> {
  return useQuery({
    queryKey: qk.operations.encounterCodeList(encounterId, query),
    queryFn: ({ signal }) => fetchEncounterCodes(encounterId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(encounterId),
    staleTime: options.staleTime,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreateDepartment(): UseMutationResult<
  DepartmentOut,
  Error,
  DepartmentCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createDepartment,
    onSuccess: (department) => {
      toast.success("Department opened", { description: department.name });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.departments(),
      });
    },
    onError: (error) => toastApiError(error, "Could not open the department"),
  });
}

export interface UpdateDepartmentVariables {
  departmentId: string;
  body: DepartmentUpdate;
}

export function useUpdateDepartment(): UseMutationResult<
  DepartmentOut,
  Error,
  UpdateDepartmentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ departmentId, body }: UpdateDepartmentVariables) =>
      updateDepartment(departmentId, body),
    onSuccess: (department) => {
      toast.success("Department updated", { description: department.name });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.departments(),
      });
    },
    onError: (error) => toastApiError(error, "Could not update the department"),
  });
}

export function useCreatePractitionerRole(): UseMutationResult<
  PractitionerRoleOut,
  Error,
  PractitionerRoleCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createPractitionerRole,
    onSuccess: (role) => {
      toast.success("Practitioner affiliated", {
        description: role.practitioner_name,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.practitioners(),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not affiliate the practitioner"),
  });
}

export interface UpdatePractitionerRoleVariables {
  roleId: string;
  body: PractitionerRoleUpdate;
}

export function useUpdatePractitionerRole(): UseMutationResult<
  PractitionerRoleOut,
  Error,
  UpdatePractitionerRoleVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ roleId, body }: UpdatePractitionerRoleVariables) =>
      updatePractitionerRole(roleId, body),
    onSuccess: (role) => {
      toast.success("Credentialing updated", {
        description: role.practitioner_name,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.practitioners(),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not update the credentialing record"),
  });
}

export function useCreateServiceItem(): UseMutationResult<
  ServiceItemOut,
  Error,
  ServiceItemCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createServiceItem,
    onSuccess: (item) => {
      toast.success("Service added", { description: item.service_display });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.serviceCatalog(),
      });
    },
    onError: (error) => toastApiError(error, "Could not add the service"),
  });
}

export interface UpdateServiceItemVariables {
  serviceItemId: string;
  body: ServiceItemUpdate;
}

export function useUpdateServiceItem(): UseMutationResult<
  ServiceItemOut,
  Error,
  UpdateServiceItemVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ serviceItemId, body }: UpdateServiceItemVariables) =>
      updateServiceItem(serviceItemId, body),
    onSuccess: (item) => {
      toast.success("Service updated", { description: item.service_display });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.serviceCatalog(),
      });
    },
    onError: (error) => toastApiError(error, "Could not update the service"),
  });
}

export interface RecordInvoicePaymentVariables {
  invoiceId: string;
  body: Omit<OperationsPaymentCreate, "idempotency_key"> & {
    idempotency_key?: string;
  };
}

export function useRecordInvoicePayment(): UseMutationResult<
  PaymentResult,
  Error,
  RecordInvoicePaymentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ invoiceId, body }: RecordInvoicePaymentVariables) =>
      recordInvoicePayment(invoiceId, {
        ...body,
        idempotency_key: body.idempotency_key ?? newIdempotencyKey(),
      }),
    onSuccess: (result) => {
      const amount = formatMoney(
        result.payment.amount_cents,
        result.payment.currency,
      );
      toast.success(result.replayed ? "Payment already on file" : `Captured ${amount}`, {
        description: `Invoice ${result.invoice.invoice_number}`,
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.invoice(result.invoice.id),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.invoices(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.revenueCycleAll(),
      });
    },
    onError: (error) => toastApiError(error, "Could not record the payment"),
  });
}

export interface RefundPaymentVariables {
  paymentId: string;
  body: RefundCreate;
}

export function useRefundPayment(): UseMutationResult<
  RefundResult,
  Error,
  RefundPaymentVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ paymentId, body }: RefundPaymentVariables) =>
      refundPayment(paymentId, body),
    onSuccess: (result) => {
      toast.success(
        `Refunded ${formatMoney(result.refund.amount_cents, result.refund.currency)}`,
        { description: `Invoice ${result.invoice.invoice_number}` },
      );
      void queryClient.invalidateQueries({
        queryKey: qk.operations.invoice(result.invoice.id),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.invoices(),
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.revenueCycleAll(),
      });
    },
    onError: (error) => toastApiError(error, "Could not refund the payment"),
  });
}

export interface CreateEncounterNoteVariables {
  encounterId: string;
  body: ClinicalNoteCreate;
}

export function useCreateEncounterNote(): UseMutationResult<
  ClinicalNoteOut,
  Error,
  CreateEncounterNoteVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ encounterId, body }: CreateEncounterNoteVariables) =>
      createEncounterNote(encounterId, body),
    onSuccess: (note) => {
      toast.success("Draft saved", { description: note.title });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.encounterNotes(note.encounter_id),
      });
    },
    onError: (error) => toastApiError(error, "Could not save the note"),
  });
}

export interface SignNoteVariables {
  noteId: string;
  body?: NoteSignRequest;
}

export function useSignNote(): UseMutationResult<
  ClinicalNoteOut,
  Error,
  SignNoteVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, body }: SignNoteVariables) =>
      signNote(noteId, body ?? {}),
    onSuccess: (note) => {
      toast.success("Note signed", {
        description: "The record is now immutable — amend it with an addendum.",
      });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.encounterNotes(note.encounter_id),
      });
    },
    onError: (error) => toastApiError(error, "Could not sign the note"),
  });
}

export interface AddNoteAddendumVariables {
  noteId: string;
  /** Only used to refresh the note list the addendum belongs to. */
  encounterId: string;
  body: AddendumCreate;
}

export function useAddNoteAddendum(): UseMutationResult<
  AddendumOut,
  Error,
  AddNoteAddendumVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ noteId, body }: AddNoteAddendumVariables) =>
      addNoteAddendum(noteId, body),
    onSuccess: (addendum, variables) => {
      toast.success(`Addendum ${addendum.sequence} signed`);
      void queryClient.invalidateQueries({
        queryKey: qk.operations.encounterNotes(variables.encounterId),
      });
    },
    onError: (error) => toastApiError(error, "Could not add the addendum"),
  });
}

export interface CreateEncounterCodeVariables {
  encounterId: string;
  body: EncounterCodeCreate;
}

export function useCreateEncounterCode(): UseMutationResult<
  EncounterCodeOut,
  Error,
  CreateEncounterCodeVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ encounterId, body }: CreateEncounterCodeVariables) =>
      createEncounterCode(encounterId, body),
    onSuccess: (code) => {
      toast.success("Code recorded", { description: code.billing_code });
      void queryClient.invalidateQueries({
        queryKey: qk.operations.encounterCodes(code.encounter_id),
      });
    },
    onError: (error) => toastApiError(error, "Could not record the code"),
  });
}

export function useCreateReferral(): UseMutationResult<
  ReferralOut,
  Error,
  ReferralCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createReferral,
    onSuccess: (referral) => {
      toast.success(
        referral.status === "sent" ? "Referral sent" : "Referral drafted",
        { description: referral.specialty_code },
      );
      void queryClient.invalidateQueries({
        queryKey: qk.operations.referrals(),
      });
    },
    onError: (error) => toastApiError(error, "Could not raise the referral"),
  });
}

export interface ChangeReferralStatusVariables {
  referralId: string;
  body: ReferralStatusChange;
}

export function useChangeReferralStatus(): UseMutationResult<
  ReferralOut,
  Error,
  ChangeReferralStatusVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ referralId, body }: ChangeReferralStatusVariables) =>
      changeReferralStatus(referralId, body),
    onSuccess: (referral) => {
      toast.success(`Referral ${referral.status.replace(/_/g, " ")}`);
      void queryClient.invalidateQueries({
        queryKey: qk.operations.referrals(),
      });
    },
    onError: (error) =>
      toastApiError(error, "Could not change the referral status"),
  });
}

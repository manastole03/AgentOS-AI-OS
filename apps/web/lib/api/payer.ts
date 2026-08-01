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
  put,
  qk,
  route,
  toastApiError,
  type PageQuery,
  type QueryHookOptions,
} from "./client";
import { formatMoney } from "./format";
import type {
  AdjudicateRequest,
  AdjudicationResult,
  AnalyticsSummary,
  BenefitGridPut,
  BenefitGridResult,
  BenefitResponse,
  ClaimResponse,
  ClaimStatus,
  CostEstimateRequest,
  CostEstimateResponse,
  DenyRequest,
  EligibilityRequest,
  EligibilityResponse,
  ExplanationPut,
  ExplanationPutResult,
  Page,
  PlanCreate,
  PlanResponse,
  PlanUpdate,
  PriorAuthDecision,
  PriorAuthResponse,
  PriorAuthStatus,
  ProductCreate,
  ProductResponse,
  ProductUpdate,
} from "./types";

/**
 * Payer operations: the products and plans an insurer sells, the claims and
 * prior authorizations it decides, and the operating summary over both.
 *
 * Backend router: `/api/v1/payer`. Every route is gated on the insurance role.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

export type ProductListQuery = PageQuery & {
  search?: string | null;
  product_type?: string | null;
  is_active?: boolean | null;
};

export type PlanListQuery = PageQuery & {
  product_id?: string | null;
  metal_tier?: string | null;
  is_active?: boolean | null;
  search?: string | null;
};

export type PlanBenefitQuery = {
  as_of?: string | null;
  include_closed?: boolean | null;
};

export type PayerClaimListQuery = PageQuery & {
  status?: ClaimStatus | null;
  payer?: string | null;
  /** Submitted-on-or-after, as `YYYY-MM-DD`. */
  from?: string | null;
  /** Submitted-on-or-before, as `YYYY-MM-DD`. */
  to?: string | null;
  patient_user_id?: string | null;
  breached_only?: boolean | null;
};

export type PriorAuthListQuery = PageQuery & {
  status?: PriorAuthStatus | null;
  patient_user_id?: string | null;
  policy_id?: string | null;
  from?: string | null;
  to?: string | null;
};

export type PayerAnalyticsQuery = {
  from?: string | null;
  to?: string | null;
};

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/payer/products */
export function fetchPayerProducts(
  query: ProductListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ProductResponse>> {
  return get<Page<ProductResponse>>("/payer/products", { query, signal });
}

/** GET /api/v1/payer/plans */
export function fetchPayerPlans(
  query: PlanListQuery = {},
  signal?: AbortSignal,
): Promise<Page<PlanResponse>> {
  return get<Page<PlanResponse>>("/payer/plans", { query, signal });
}

/** GET /api/v1/payer/plans/{plan_id}/benefits */
export function fetchPlanBenefits(
  planId: string,
  query: PlanBenefitQuery = {},
  signal?: AbortSignal,
): Promise<BenefitResponse[]> {
  return get<BenefitResponse[]>(route`/payer/plans/${planId}/benefits`, {
    query,
    signal,
  });
}

/** GET /api/v1/payer/claims */
export function fetchPayerClaims(
  query: PayerClaimListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ClaimResponse>> {
  return get<Page<ClaimResponse>>("/payer/claims", { query, signal });
}

/** GET /api/v1/payer/prior-authorizations */
export function fetchPriorAuthorizations(
  query: PriorAuthListQuery = {},
  signal?: AbortSignal,
): Promise<Page<PriorAuthResponse>> {
  return get<Page<PriorAuthResponse>>("/payer/prior-authorizations", {
    query,
    signal,
  });
}

/** GET /api/v1/payer/cost-estimates/{estimate_id} */
export function fetchCostEstimate(
  estimateId: string,
  signal?: AbortSignal,
): Promise<CostEstimateResponse> {
  return get<CostEstimateResponse>(route`/payer/cost-estimates/${estimateId}`, {
    signal,
  });
}

/** GET /api/v1/payer/analytics/summary */
export function fetchPayerAnalytics(
  query: PayerAnalyticsQuery = {},
  signal?: AbortSignal,
): Promise<AnalyticsSummary> {
  return get<AnalyticsSummary>("/payer/analytics/summary", { query, signal });
}

/** POST /api/v1/payer/products */
export function createPayerProduct(
  body: ProductCreate,
): Promise<ProductResponse> {
  return post<ProductResponse>("/payer/products", body);
}

/** PATCH /api/v1/payer/products/{product_id} */
export function updatePayerProduct(
  productId: string,
  body: ProductUpdate,
): Promise<ProductResponse> {
  return patch<ProductResponse>(route`/payer/products/${productId}`, body);
}

/** POST /api/v1/payer/plans */
export function createPayerPlan(body: PlanCreate): Promise<PlanResponse> {
  return post<PlanResponse>("/payer/plans", body);
}

/** PATCH /api/v1/payer/plans/{plan_id} */
export function updatePayerPlan(
  planId: string,
  body: PlanUpdate,
): Promise<PlanResponse> {
  return patch<PlanResponse>(route`/payer/plans/${planId}`, body);
}

/**
 * PUT /api/v1/payer/plans/{plan_id}/benefits
 *
 * The payload is the whole grid: rows left out are closed on
 * `close_omitted_on` rather than deleted, so history stays intact.
 */
export function replacePlanBenefits(
  planId: string,
  body: BenefitGridPut,
): Promise<BenefitGridResult> {
  return put<BenefitGridResult>(route`/payer/plans/${planId}/benefits`, body);
}

/** PUT /api/v1/payer/plans/{plan_id}/explanations */
export function upsertPlanExplanations(
  planId: string,
  body: ExplanationPut,
): Promise<ExplanationPutResult> {
  return put<ExplanationPutResult>(
    route`/payer/plans/${planId}/explanations`,
    body,
  );
}

/** POST /api/v1/payer/eligibility/check */
export function runEligibilityCheck(
  body: EligibilityRequest,
): Promise<EligibilityResponse> {
  return post<EligibilityResponse>("/payer/eligibility/check", body);
}

/** POST /api/v1/payer/claims/{claim_id}/adjudicate */
export function adjudicateClaim(
  claimId: string,
  body: AdjudicateRequest,
): Promise<AdjudicationResult> {
  return post<AdjudicationResult>(
    route`/payer/claims/${claimId}/adjudicate`,
    body,
  );
}

/** POST /api/v1/payer/claims/{claim_id}/deny */
export function denyClaim(
  claimId: string,
  body: DenyRequest,
): Promise<ClaimResponse> {
  return post<ClaimResponse>(route`/payer/claims/${claimId}/deny`, body);
}

/** POST /api/v1/payer/prior-authorizations/{auth_id}/decide */
export function decidePriorAuthorization(
  authId: string,
  body: PriorAuthDecision,
): Promise<PriorAuthResponse> {
  return post<PriorAuthResponse>(
    route`/payer/prior-authorizations/${authId}/decide`,
    body,
  );
}

/** POST /api/v1/payer/cost-estimates */
export function createCostEstimate(
  body: CostEstimateRequest,
): Promise<CostEstimateResponse> {
  return post<CostEstimateResponse>("/payer/cost-estimates", body);
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function usePayerProducts(
  query: ProductListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ProductResponse>> {
  return useQuery({
    queryKey: qk.payer.productList(query),
    queryFn: ({ signal }) => fetchPayerProducts(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function usePayerPlans(
  query: PlanListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<PlanResponse>> {
  return useQuery({
    queryKey: qk.payer.planList(query),
    queryFn: ({ signal }) => fetchPayerPlans(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function usePlanBenefits(
  planId: string,
  query: PlanBenefitQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<BenefitResponse[]> {
  return useQuery({
    queryKey: qk.payer.planBenefits(planId, query),
    queryFn: ({ signal }) => fetchPlanBenefits(planId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(planId),
    staleTime: options.staleTime,
  });
}

export function usePayerClaims(
  query: PayerClaimListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ClaimResponse>> {
  return useQuery({
    queryKey: qk.payer.claimList(query),
    queryFn: ({ signal }) => fetchPayerClaims(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function usePriorAuthorizations(
  query: PriorAuthListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<PriorAuthResponse>> {
  return useQuery({
    queryKey: qk.payer.priorAuthList(query),
    queryFn: ({ signal }) => fetchPriorAuthorizations(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useCostEstimate(
  estimateId: string,
  options: QueryHookOptions = {},
): UseQueryResult<CostEstimateResponse> {
  return useQuery({
    queryKey: qk.payer.costEstimate(estimateId),
    queryFn: ({ signal }) => fetchCostEstimate(estimateId, signal),
    enabled: (options.enabled ?? true) && Boolean(estimateId),
    staleTime: options.staleTime,
  });
}

export function usePayerAnalytics(
  query: PayerAnalyticsQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<AnalyticsSummary> {
  return useQuery({
    queryKey: qk.payer.analytics(query),
    queryFn: ({ signal }) => fetchPayerAnalytics(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

// ---------------------------------------------------------------------------
// Mutation hooks
// ---------------------------------------------------------------------------

export function useCreatePayerProduct(): UseMutationResult<
  ProductResponse,
  Error,
  ProductCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createPayerProduct,
    onSuccess: (product) => {
      toast.success("Product filed", { description: product.name });
      void queryClient.invalidateQueries({ queryKey: qk.payer.products() });
    },
    onError: (error) => toastApiError(error, "Could not create the product"),
  });
}

export interface UpdatePayerProductVariables {
  productId: string;
  body: ProductUpdate;
}

export function useUpdatePayerProduct(): UseMutationResult<
  ProductResponse,
  Error,
  UpdatePayerProductVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, body }: UpdatePayerProductVariables) =>
      updatePayerProduct(productId, body),
    onSuccess: (product) => {
      toast.success("Product updated", { description: product.name });
      void queryClient.invalidateQueries({ queryKey: qk.payer.products() });
    },
    onError: (error) => toastApiError(error, "Could not update the product"),
  });
}

export function useCreatePayerPlan(): UseMutationResult<
  PlanResponse,
  Error,
  PlanCreate
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createPayerPlan,
    onSuccess: (plan) => {
      toast.success("Plan created", { description: plan.name });
      void queryClient.invalidateQueries({ queryKey: qk.payer.plans() });
      void queryClient.invalidateQueries({ queryKey: qk.payer.products() });
    },
    onError: (error) => toastApiError(error, "Could not create the plan"),
  });
}

export interface UpdatePayerPlanVariables {
  planId: string;
  body: PlanUpdate;
}

export function useUpdatePayerPlan(): UseMutationResult<
  PlanResponse,
  Error,
  UpdatePayerPlanVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, body }: UpdatePayerPlanVariables) =>
      updatePayerPlan(planId, body),
    onSuccess: (plan) => {
      toast.success("Plan updated", { description: plan.name });
      void queryClient.invalidateQueries({ queryKey: qk.payer.plans() });
    },
    onError: (error) => toastApiError(error, "Could not update the plan"),
  });
}

export interface ReplacePlanBenefitsVariables {
  planId: string;
  body: BenefitGridPut;
}

export function useReplacePlanBenefits(): UseMutationResult<
  BenefitGridResult,
  Error,
  ReplacePlanBenefitsVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, body }: ReplacePlanBenefitsVariables) =>
      replacePlanBenefits(planId, body),
    onSuccess: (result) => {
      toast.success("Benefit grid saved", {
        description: `${result.created} added · ${result.updated} updated · ${result.closed} closed`,
      });
      void queryClient.invalidateQueries({ queryKey: qk.payer.plans() });
    },
    onError: (error) => toastApiError(error, "Could not save the benefit grid"),
  });
}

export interface UpsertPlanExplanationsVariables {
  planId: string;
  body: ExplanationPut;
}

export function useUpsertPlanExplanations(): UseMutationResult<
  ExplanationPutResult,
  Error,
  UpsertPlanExplanationsVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ planId, body }: UpsertPlanExplanationsVariables) =>
      upsertPlanExplanations(planId, body),
    onSuccess: (result) => {
      toast.success("Plain-language text published", {
        description: `${result.created} written · ${result.updated} revised — members see this immediately`,
      });
      void queryClient.invalidateQueries({ queryKey: qk.payer.plans() });
    },
    onError: (error) =>
      toastApiError(error, "Could not publish the explanations"),
  });
}

export function useEligibilityCheck(): UseMutationResult<
  EligibilityResponse,
  Error,
  EligibilityRequest
> {
  return useMutation({
    mutationFn: runEligibilityCheck,
    onSuccess: (response) => {
      toast.success(
        response.coverage_found ? "Coverage found" : "No coverage found",
        {
          description: response.from_cache
            ? "Served from the eligibility cache"
            : "Fresh check against the payer of record",
        },
      );
    },
    onError: (error) => toastApiError(error, "Eligibility check failed"),
  });
}

export interface AdjudicateClaimVariables {
  claimId: string;
  body: AdjudicateRequest;
}

export function useAdjudicateClaim(): UseMutationResult<
  AdjudicationResult,
  Error,
  AdjudicateClaimVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, body }: AdjudicateClaimVariables) =>
      adjudicateClaim(claimId, body),
    onSuccess: (result) => {
      toast.success(`Claim ${result.claim.claim_number} ${result.claim.status}`, {
        description: `${formatMoney(
          result.claim.paid_cents,
          result.claim.currency,
        )} to the provider · ${
          result.accumulators_applied
            ? "accumulators moved"
            : "accumulators already applied"
        }`,
      });
      void queryClient.invalidateQueries({ queryKey: qk.payer.claims() });
      void queryClient.invalidateQueries({ queryKey: qk.payer.analyticsAll() });
    },
    onError: (error) => toastApiError(error, "Could not adjudicate the claim"),
  });
}

export interface DenyClaimVariables {
  claimId: string;
  body: DenyRequest;
}

export function useDenyClaim(): UseMutationResult<
  ClaimResponse,
  Error,
  DenyClaimVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ claimId, body }: DenyClaimVariables) =>
      denyClaim(claimId, body),
    onSuccess: (claim) => {
      toast.success(`Claim ${claim.claim_number} denied`, {
        description: `Reason code ${claim.denial_reason_code ?? "recorded"}`,
      });
      void queryClient.invalidateQueries({ queryKey: qk.payer.claims() });
      void queryClient.invalidateQueries({ queryKey: qk.payer.analyticsAll() });
    },
    onError: (error) => toastApiError(error, "Could not deny the claim"),
  });
}

export interface DecidePriorAuthVariables {
  authId: string;
  body: PriorAuthDecision;
}

export function useDecidePriorAuthorization(): UseMutationResult<
  PriorAuthResponse,
  Error,
  DecidePriorAuthVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ authId, body }: DecidePriorAuthVariables) =>
      decidePriorAuthorization(authId, body),
    onSuccess: (auth) => {
      toast.success(
        `Prior authorization ${auth.status.replace(/_/g, " ")}`,
        {
          description:
            auth.authorization_number ?? auth.decision_reason ?? undefined,
        },
      );
      void queryClient.invalidateQueries({ queryKey: qk.payer.priorAuths() });
      void queryClient.invalidateQueries({ queryKey: qk.payer.analyticsAll() });
    },
    onError: (error) => toastApiError(error, "Could not record the decision"),
  });
}

export function useCreateCostEstimate(): UseMutationResult<
  CostEstimateResponse,
  Error,
  CostEstimateRequest
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createCostEstimate,
    onSuccess: (estimate) => {
      toast.success("Estimate created", {
        description: `${formatMoney(
          estimate.member_liability_cents,
          estimate.currency,
        )} member liability`,
      });
      queryClient.setQueryData(qk.payer.costEstimate(estimate.id), estimate);
    },
    onError: (error) => toastApiError(error, "Could not create the estimate"),
  });
}

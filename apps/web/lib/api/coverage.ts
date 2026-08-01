import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import {
  get,
  qk,
  route,
  type PageQuery,
  type QueryHookOptions,
} from "./client";
import type {
  ClaimAssistance,
  ClaimDetail,
  ClaimSummary,
  CoverageExplanation,
  LoyaltyBalance,
  MarketplaceResponse,
  Page,
  PlanDetail,
  PolicySummary,
} from "./types";

/**
 * Member-facing coverage: the policies a person holds, what they actually
 * cover in plain language, their claims, the plan marketplace and the loyalty
 * balance that discounts a purchase.
 *
 * Backend router: `/api/v1/coverage`.
 */

// ---------------------------------------------------------------------------
// Query parameters
// ---------------------------------------------------------------------------

export type MarketplaceSort = "recommended" | "premium_asc" | "deductible_asc";

export type PolicyQuery = {
  /** Only a delegate (clinician, payer, admin) supplies this. */
  patient_user_id?: string | null;
};

export type CoverageExplanationQuery = {
  patient_user_id?: string | null;
  locale?: string | null;
  reading_level?: string | null;
  benefit_year?: number | null;
};

export type CoverageClaimListQuery = PageQuery &
  PolicyQuery & {
    policy_id?: string | null;
    status?: string | null;
    service_from?: string | null;
    service_to?: string | null;
  };

export type MarketplaceQuery = PageQuery &
  PolicyQuery & {
    sort?: MarketplaceSort | null;
    product_type?: string | null;
    metal_tier?: string | null;
    payer_organization_id?: string | null;
    currency?: string | null;
    max_premium_cents?: number | null;
    max_deductible_cents?: number | null;
  };

export type LoyaltyQuery = PageQuery & PolicyQuery;

// ---------------------------------------------------------------------------
// Fetchers
// ---------------------------------------------------------------------------

/** GET /api/v1/coverage/me/policies */
export function fetchMyPolicies(
  query: PolicyQuery = {},
  signal?: AbortSignal,
): Promise<PolicySummary[]> {
  return get<PolicySummary[]>("/coverage/me/policies", { query, signal });
}

/** GET /api/v1/coverage/policies/{policy_id}/explain */
export function fetchCoverageExplanation(
  policyId: string,
  query: CoverageExplanationQuery = {},
  signal?: AbortSignal,
): Promise<CoverageExplanation> {
  return get<CoverageExplanation>(
    route`/coverage/policies/${policyId}/explain`,
    { query, signal },
  );
}

/** GET /api/v1/coverage/me/claim-assistance */
export function fetchClaimAssistance(
  query: PolicyQuery = {},
  signal?: AbortSignal,
): Promise<ClaimAssistance> {
  return get<ClaimAssistance>("/coverage/me/claim-assistance", {
    query,
    signal,
  });
}

/** GET /api/v1/coverage/claims */
export function fetchCoverageClaims(
  query: CoverageClaimListQuery = {},
  signal?: AbortSignal,
): Promise<Page<ClaimSummary>> {
  return get<Page<ClaimSummary>>("/coverage/claims", { query, signal });
}

/** GET /api/v1/coverage/claims/{claim_id} */
export function fetchCoverageClaim(
  claimId: string,
  signal?: AbortSignal,
): Promise<ClaimDetail> {
  return get<ClaimDetail>(route`/coverage/claims/${claimId}`, { signal });
}

/** GET /api/v1/coverage/marketplace */
export function fetchMarketplace(
  query: MarketplaceQuery = {},
  signal?: AbortSignal,
): Promise<MarketplaceResponse> {
  return get<MarketplaceResponse>("/coverage/marketplace", { query, signal });
}

/** GET /api/v1/coverage/marketplace/plans/{plan_id} */
export function fetchMarketplacePlan(
  planId: string,
  query: { locale?: string | null; reading_level?: string | null } = {},
  signal?: AbortSignal,
): Promise<PlanDetail> {
  return get<PlanDetail>(route`/coverage/marketplace/plans/${planId}`, {
    query,
    signal,
  });
}

/** GET /api/v1/coverage/me/loyalty */
export function fetchLoyaltyBalance(
  query: LoyaltyQuery = {},
  signal?: AbortSignal,
): Promise<LoyaltyBalance> {
  return get<LoyaltyBalance>("/coverage/me/loyalty", { query, signal });
}

// ---------------------------------------------------------------------------
// Read hooks
// ---------------------------------------------------------------------------

export function useMyPolicies(
  query: PolicyQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<PolicySummary[]> {
  return useQuery({
    queryKey: qk.coverage.policyList(query),
    queryFn: ({ signal }) => fetchMyPolicies(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useCoverageExplanation(
  policyId: string,
  query: CoverageExplanationQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<CoverageExplanation> {
  return useQuery({
    queryKey: qk.coverage.policyExplanation(policyId, query),
    queryFn: ({ signal }) => fetchCoverageExplanation(policyId, query, signal),
    enabled: (options.enabled ?? true) && Boolean(policyId),
    staleTime: options.staleTime,
  });
}

export function useClaimAssistance(
  query: PolicyQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<ClaimAssistance> {
  return useQuery({
    queryKey: qk.coverage.claimAssistance(query),
    queryFn: ({ signal }) => fetchClaimAssistance(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useCoverageClaims(
  query: CoverageClaimListQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<Page<ClaimSummary>> {
  return useQuery({
    queryKey: qk.coverage.claimList(query),
    queryFn: ({ signal }) => fetchCoverageClaims(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useCoverageClaim(
  claimId: string,
  options: QueryHookOptions = {},
): UseQueryResult<ClaimDetail> {
  return useQuery({
    queryKey: qk.coverage.claim(claimId),
    queryFn: ({ signal }) => fetchCoverageClaim(claimId, signal),
    enabled: (options.enabled ?? true) && Boolean(claimId),
    staleTime: options.staleTime,
  });
}

export function useMarketplace(
  query: MarketplaceQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<MarketplaceResponse> {
  return useQuery({
    queryKey: qk.coverage.marketplaceList(query),
    queryFn: ({ signal }) => fetchMarketplace(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

export function useLoyaltyBalance(
  query: LoyaltyQuery = {},
  options: QueryHookOptions = {},
): UseQueryResult<LoyaltyBalance> {
  return useQuery({
    queryKey: qk.coverage.loyaltyBalance(query),
    queryFn: ({ signal }) => fetchLoyaltyBalance(query, signal),
    enabled: options.enabled ?? true,
    staleTime: options.staleTime,
  });
}

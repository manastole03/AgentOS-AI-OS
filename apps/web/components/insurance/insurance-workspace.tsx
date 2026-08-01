"use client";

import { useMemo } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import { Badge } from "@healthos/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@healthos/ui/card";
import { DataTable } from "@healthos/ui/data-table";
import { EmptyState } from "@healthos/ui/empty-state";
import { PageHeader } from "@healthos/ui/page-header";
import { Section } from "@healthos/ui/section";
import { StatTile } from "@healthos/ui/stat-tile";
import { StatusBadge, statusTone } from "@healthos/ui/status-badge";
import {
  BadgeDollarSign,
  Landmark,
  ReceiptText,
  ShieldCheck,
} from "lucide-react";
import {
  useCoverageClaims,
  useLoyaltyBalance,
  useMarketplace,
  useMyPolicies,
} from "@/lib/api/coverage";
import { formatDate, formatMoney } from "@/lib/api/format";
import type { ClaimSummary, MarketplacePlan, PolicySummary } from "@/lib/api/types";
import { Panel, StatRowSkeleton } from "@/components/workspace/workspace-state";

/**
 * The member's own view of coverage: what they hold, what has been claimed, and
 * what the marketplace recommends against their history.
 */

const claimColumns: ColumnDef<ClaimSummary>[] = [
  {
    accessorKey: "claim_number",
    header: "Claim",
    cell: ({ row }) => (
      <span className="font-mono text-xs tabular">
        {row.original.claim_number}
      </span>
    ),
  },
  {
    id: "service",
    header: "Service dates",
    cell: ({ row }) =>
      `${formatDate(row.original.service_from)} – ${formatDate(row.original.service_to)}`,
  },
  {
    accessorKey: "total_charge_cents",
    header: "Billed",
    cell: ({ row }) =>
      formatMoney(row.original.total_charge_cents, row.original.currency),
    meta: { numeric: true },
  },
  {
    accessorKey: "paid_cents",
    header: "Plan paid",
    cell: ({ row }) =>
      formatMoney(row.original.paid_cents, row.original.currency, {
        fallback: "Pending",
      }),
    meta: { numeric: true },
  },
  {
    accessorKey: "patient_responsibility_cents",
    header: "You owe",
    cell: ({ row }) =>
      formatMoney(
        row.original.patient_responsibility_cents,
        row.original.currency,
        { fallback: "Pending" },
      ),
    meta: { numeric: true },
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <StatusBadge
        tone={statusTone(row.original.status)}
        label={row.original.status.replace(/_/g, " ")}
        size="sm"
      />
    ),
  },
];

function PolicyCard({ policy }: { policy: PolicySummary }) {
  return (
    <Card>
      <CardHeader className="space-y-1.5">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="text-base">{policy.plan.name}</CardTitle>
          <StatusBadge
            tone={statusTone(policy.status)}
            label={policy.status}
            size="sm"
          />
        </div>
        <p className="text-sm text-muted-foreground">
          {policy.plan.payer.legal_name} · {policy.plan.product_name}
        </p>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-muted-foreground">Member ID</p>
          <p className="font-mono tabular">{policy.member_id}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Policy number</p>
          <p className="font-mono tabular">{policy.policy_number}</p>
        </div>
        <div>
          <p className="text-muted-foreground">Premium</p>
          <p className="tabular">
            {formatMoney(policy.premium_cents, policy.currency)} ·{" "}
            {policy.premium_frequency}
          </p>
        </div>
        <div>
          <p className="text-muted-foreground">Deductible</p>
          <p className="tabular">
            {formatMoney(
              policy.plan.individual_deductible_cents,
              policy.plan.currency,
              { fallback: "Not applicable" },
            )}
          </p>
        </div>
        <div className="col-span-2">
          <p className="text-muted-foreground">Effective</p>
          <p className="tabular">
            {formatDate(policy.effective_from)} –{" "}
            {formatDate(policy.effective_to, { fallback: "open ended" })}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendedPlan({ candidate }: { candidate: MarketplacePlan }) {
  const { plan } = candidate;
  return (
    <li className="flex flex-wrap items-start justify-between gap-4 py-4">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">{plan.name}</p>
          {plan.metal_tier ? (
            <Badge variant="secondary" className="capitalize">
              {plan.metal_tier}
            </Badge>
          ) : null}
        </div>
        <p className="text-sm text-muted-foreground">
          {plan.payer.legal_name} · {candidate.covered_benefit_count} of{" "}
          {candidate.benefit_count} benefits covered
        </p>
        {candidate.reasons.length ? (
          <p className="text-sm text-muted-foreground">
            {candidate.reasons[0]?.detail ?? candidate.reasons[0]?.code}
          </p>
        ) : null}
      </div>
      <div className="text-right">
        <p className="font-mono text-lg font-semibold tabular">
          {formatMoney(plan.premium_cents, plan.currency)}
        </p>
        <p className="text-xs text-muted-foreground">
          premium · est.{" "}
          <span className="tabular">
            {formatMoney(
              candidate.estimated_annual_cost_cents,
              plan.currency,
              { compact: true },
            )}
          </span>{" "}
          a year
        </p>
      </div>
    </li>
  );
}

export function InsuranceWorkspace() {
  const policies = useMyPolicies();
  const claims = useCoverageClaims({ limit: 50 });
  const loyalty = useLoyaltyBalance();
  const marketplace = useMarketplace({ limit: 5, sort: "recommended" });

  const owed = useMemo(
    () =>
      (claims.data?.items ?? []).reduce(
        (total, claim) => total + (claim.patient_responsibility_cents ?? 0),
        0,
      ),
    [claims.data],
  );
  const currency = claims.data?.items[0]?.currency ?? "USD";
  const activePolicies = (policies.data ?? []).filter(
    (policy) => policy.status === "active",
  );

  return (
    <div className="space-y-8">
      <PageHeader
        title="Coverage"
        description="Policies, claims, loyalty points, and plans matched to your history."
      />

      {policies.isPending || claims.isPending ? (
        <StatRowSkeleton />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Active policies"
            value={activePolicies.length}
            icon={ShieldCheck}
          />
          <StatTile
            label="Claims on file"
            value={claims.data?.total ?? claims.data?.items.length ?? 0}
            icon={ReceiptText}
          />
          <StatTile
            label="Your responsibility"
            value={formatMoney(owed, currency)}
            icon={BadgeDollarSign}
          />
          <StatTile
            label="Loyalty points"
            value={loyalty.data?.balance_points ?? 0}
            icon={Landmark}
          />
        </div>
      )}

      <Section
        title="Your policies"
        description="Coverage currently attached to your Health ID."
      >
        <Panel
          isPending={policies.isPending}
          error={policies.error}
          errorTitle="Policies could not be loaded"
        >
          {policies.data?.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {policies.data.map((policy) => (
                <PolicyCard key={policy.id} policy={policy} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={ShieldCheck}
              size="sm"
              title="No policy on file"
              description="Buy or link a policy to see benefits and claims here."
            />
          )}
        </Panel>
      </Section>

      <Section
        title="Claims"
        description="Submission, adjudication, and what you are left to pay."
        flush
        contentClassName="px-6"
      >
        <Panel
          isPending={claims.isPending}
          error={claims.error}
          errorTitle="Claims could not be loaded"
        >
          <DataTable
            columns={claimColumns}
            data={claims.data?.items ?? []}
            searchKey="claim_number"
            searchPlaceholder="Search by claim number…"
            emptyMessage="No claims submitted"
            caption="Coverage claims"
            getRowId={(row) => row.id}
          />
        </Panel>
      </Section>

      <Section
        title="Recommended plans"
        description="Ranked against your recorded history and loyalty balance. An estimate, not a quote."
      >
        <Panel
          isPending={marketplace.isPending}
          error={marketplace.error}
          errorTitle="The marketplace could not be loaded"
        >
          {marketplace.data?.plans.items.length ? (
            <ul className="divide-y">
              {marketplace.data.plans.items.map((candidate) => (
                <RecommendedPlan
                  key={candidate.recommendation_id}
                  candidate={candidate}
                />
              ))}
            </ul>
          ) : (
            <EmptyState
              icon={Landmark}
              size="sm"
              title="No plans to compare"
              description="No marketplace product currently matches your profile."
            />
          )}
        </Panel>
      </Section>
    </div>
  );
}

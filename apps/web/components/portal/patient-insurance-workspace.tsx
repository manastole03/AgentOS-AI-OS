"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import type { PortalRecord } from "@healthos/api-types";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { Badge } from "@healthos/ui/badge";
import { Headphones, ShieldCheck, Sparkles } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { PageHeading } from "@/components/portal/page-heading";

interface PolicyOffer {
  id: string;
  payer: string;
  plan_name: string;
  coverage_type?: string;
  plain_language_coverage?: string;
  monthly_premium_cents?: number;
  currency: string;
  loyalty_points_available: number;
  ranking_score: number;
  match_reasons?: string[];
  disclaimer: string;
}

export function PatientInsuranceWorkspace({
  marketplace = false,
}: {
  marketplace?: boolean;
}) {
  const [policies, setPolicies] = useState<PortalRecord[]>([]);
  const [offers, setOffers] = useState<PolicyOffer[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      if (marketplace)
        setOffers(
          await authenticatedFetch(
            "/api/v1/portal/patient/insurance/marketplace",
          ),
        );
      else
        setPolicies(
          await authenticatedFetch("/api/v1/portal/resources/insurance"),
        );
    } catch (value) {
      setError(
        value instanceof Error
          ? value.message
          : "Unable to load insurance information",
      );
    }
  }, [marketplace]);
  useEffect(() => void load(), [load]);

  async function purchase(offer: PolicyOffer) {
    setError(null);
    try {
      await authenticatedFetch("/api/v1/portal/patient/insurance/purchase", {
        method: "POST",
        body: JSON.stringify({
          policy_id: offer.id,
          loyalty_points: 0,
          applicant_details: {},
        }),
      });
      setMessage(
        "Enrollment started. The policy now appears under active insurance as pending insurer confirmation.",
      );
    } catch (value) {
      setError(
        value instanceof Error ? value.message : "Unable to start enrollment",
      );
    }
  }

  return (
    <>
      <PageHeading
        eyebrow="Insurance"
        title={marketplace ? "Buy insurance" : "Coverage & claims"}
        description={
          marketplace
            ? "Compare participating plans ranked for your profile and available loyalty benefits."
            : "Understand current coverage in plain language and get help filing a claim."
        }
      />
      {error ? (
        <p className="mb-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="mb-5 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">
          {message}
        </p>
      ) : null}
      {!marketplace ? (
        <Card className="mb-6 border-emerald-200 bg-emerald-50/60">
          <CardContent className="flex flex-col gap-4 pt-6 sm:flex-row sm:items-center">
            <span className="grid size-11 place-items-center rounded-full bg-emerald-600 text-white">
              <Headphones className="size-5" />
            </span>
            <div className="flex-1">
              <p className="font-semibold">Need help with a claim?</p>
              <p className="text-sm text-muted-foreground">
                Call the claim-assistance line at{" "}
                <a
                  className="font-semibold text-foreground"
                  href="tel:+18004325867"
                >
                  1-800-HEALTHOS
                </a>
                . An agent can guide you through submission and appeals.
              </p>
            </div>
            <Button asChild>
              <Link href="/portal/claims">Initiate a claim</Link>
            </Button>
          </CardContent>
        </Card>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-2">
        {(marketplace ? offers : policies).map((item) => {
          const offer = item as PolicyOffer;
          const policy = item as PortalRecord;
          const data = policy.data ?? {};
          const title = marketplace ? offer.plan_name : policy.title;
          const coverage = marketplace
            ? offer.plain_language_coverage
            : String(
                data.plain_language_coverage ??
                  "Open the issued policy documents for exact benefits, limits, and exclusions.",
              );
          const amount = marketplace
            ? offer.monthly_premium_cents
            : policy.amount_cents;
          const currency = marketplace
            ? offer.currency
            : (policy.currency ?? "USD");
          return (
            <Card key={marketplace ? offer.id : policy.id}>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <ShieldCheck className="size-5 text-emerald-600" />
                  {marketplace ? (
                    <Badge variant="secondary">
                      <Sparkles className="mr-1 size-3" />
                      Match {offer.ranking_score}
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="capitalize">
                      {policy.status}
                    </Badge>
                  )}
                </div>
                <CardTitle className="mt-3">{title}</CardTitle>
                <CardDescription>
                  {marketplace
                    ? `${offer.payer} · ${offer.coverage_type ?? "Medical"}`
                    : String(data.payer ?? "Active coverage")}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-sm leading-6">{coverage}</p>
                {amount != null ? (
                  <p className="font-semibold">
                    {new Intl.NumberFormat("en-US", {
                      style: "currency",
                      currency,
                    }).format(amount / 100)}
                    {marketplace ? " / month" : ""}
                  </p>
                ) : null}
                {marketplace ? (
                  <>
                    <p className="text-xs text-muted-foreground">
                      {offer.disclaimer} · {offer.loyalty_points_available}{" "}
                      loyalty points available.
                    </p>
                    {offer.match_reasons?.length ? (
                      <p className="text-xs text-emerald-700">
                        Matched to: {offer.match_reasons.join(", ")}
                      </p>
                    ) : null}
                    <Button
                      className="w-full"
                      onClick={() => void purchase(offer)}
                    >
                      Select and enroll
                    </Button>
                  </>
                ) : (
                  <Button variant="outline" asChild>
                    <Link href="/portal/claims">Start a claim</Link>
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </>
  );
}

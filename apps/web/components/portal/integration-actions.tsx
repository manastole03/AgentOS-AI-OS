"use client";

import { useState } from "react";
import { Button } from "@healthos/ui/button";
import { Card, CardContent } from "@healthos/ui/card";
import { Bot, Cable, CreditCard, DatabaseZap } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";

export function IntegrationActions({
  module,
  onComplete,
}: {
  module: string;
  onComplete: () => Promise<void>;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const fhir = [
    "medical_history",
    "vaccinations",
    "lab_reports",
    "appointments",
    "patients",
    "prescriptions",
  ].includes(module);
  const insurance = [
    "insurance",
    "eligibility",
    "claims",
    "prior_authorization",
    "policies",
  ].includes(module);
  const payment = ["payments", "billing"].includes(module);
  const fraud = module === "fraud_detection";
  if (!fhir && !insurance && !payment && !fraud) return null;
  async function run(kind: "fhir" | "insurance" | "payment" | "fraud") {
    setMessage("Connecting securely…");
    try {
      if (kind === "fhir") {
        const reference = window.prompt("FHIR Patient resource ID");
        if (!reference) return;
        const result = await authenticatedFetch<{
          status: string;
          imported: number;
        }>("/api/v1/portal/integrations/fhir", {
          method: "POST",
          body: JSON.stringify({ patient_reference: reference }),
        });
        setMessage(`${result.status}: ${result.imported} resources imported`);
      } else if (kind === "insurance") {
        const result = await authenticatedFetch<{ status: string }>(
          "/api/v1/portal/integrations/insurance",
          {
            method: "POST",
            body: JSON.stringify({ operation: module, parameters: {} }),
          },
        );
        setMessage(`Insurance API: ${result.status}`);
      } else if (kind === "payment") {
        const amount = window.prompt("Payment amount in USD");
        if (!amount) return;
        const result = await authenticatedFetch<{ status: string }>(
          "/api/v1/portal/payments/intents",
          {
            method: "POST",
            headers: { "Idempotency-Key": crypto.randomUUID() },
            body: JSON.stringify({
              amount_cents: Math.round(Number(amount) * 100),
              currency: "usd",
              description: "HealthOS account payment",
            }),
          },
        );
        setMessage(`Payment intent: ${result.status}`);
      } else {
        const evidence = window.prompt(
          "Describe the transaction or claim indicators to analyze",
        );
        if (!evidence) return;
        const result = await authenticatedFetch<{ response?: string }>(
          "/ai/v1/runs",
          {
            method: "POST",
            body: JSON.stringify({
              prompt: `Analyze these insurance fraud indicators as decision support. Do not make a final determination: ${evidence}`,
              team: "insurance",
              execution_mode: "sync",
              memory_mode: "none",
            }),
          },
        );
        setMessage(result.response || "Risk analysis completed");
      }
      await onComplete();
    } catch (value) {
      setMessage(value instanceof Error ? value.message : "Integration failed");
    }
  }
  return (
    <Card className="mb-6 border-dashed">
      <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
        <div className="mr-auto">
          <p className="text-sm font-medium">Connected workflow</p>
          <p className="text-xs text-muted-foreground">
            {message ?? "Synchronize with configured external systems."}
          </p>
        </div>
        {fhir ? (
          <Button size="sm" variant="outline" onClick={() => void run("fhir")}>
            <DatabaseZap className="mr-2 size-4" />
            FHIR sync
          </Button>
        ) : null}
        {insurance ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void run("insurance")}
          >
            <Cable className="mr-2 size-4" />
            Insurance API
          </Button>
        ) : null}
        {payment ? (
          <Button
            size="sm"
            variant="outline"
            onClick={() => void run("payment")}
          >
            <CreditCard className="mr-2 size-4" />
            Payment gateway
          </Button>
        ) : null}
        {fraud ? (
          <Button size="sm" variant="outline" onClick={() => void run("fraud")}>
            <Bot className="mr-2 size-4" />
            Analyze risk
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

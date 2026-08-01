"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { Input } from "@healthos/ui/input";
import { CalendarDays, CircleDashed, FlaskConical } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { PageHeading } from "@/components/portal/page-heading";

interface Slot {
  id: string;
  provider?: string;
  laboratory?: string;
  specialty?: string;
  test_code?: string;
  test_name?: string;
  location?: string;
  starts_at: string;
  fee_cents?: number;
  price_cents?: number;
  currency: string;
}

export function PatientBookingWorkspace({
  kind,
}: {
  kind: "appointments" | "labs";
}) {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [reason, setReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      setSlots(
        await authenticatedFetch<Slot[]>(
          kind === "appointments"
            ? "/api/v1/portal/patient/providers/availability"
            : "/api/v1/portal/patient/labs/availability",
        ),
      );
    } catch (value) {
      setError(
        value instanceof Error ? value.message : "Unable to load availability",
      );
    }
  }, [kind]);
  useEffect(() => void load(), [load]);

  async function book(slot: Slot) {
    setBusy(slot.id);
    setError(null);
    try {
      if (kind === "appointments") {
        let paymentId: string | null = null;
        if ((slot.fee_cents ?? 0) > 0) {
          const payment = await authenticatedFetch<{ payment_id: string }>(
            "/api/v1/portal/payments/intents",
            {
              method: "POST",
              headers: { "Idempotency-Key": crypto.randomUUID() },
              body: JSON.stringify({
                amount_cents: slot.fee_cents,
                currency: slot.currency,
                description: `Consultation with ${slot.provider}`,
              }),
            },
          );
          paymentId = payment.payment_id;
        }
        await authenticatedFetch("/api/v1/portal/patient/appointments/book", {
          method: "POST",
          body: JSON.stringify({
            slot_id: slot.id,
            reason: reason || "Consultation",
            payment_id: paymentId,
          }),
        });
      } else {
        await authenticatedFetch("/api/v1/portal/patient/labs/book", {
          method: "POST",
          body: JSON.stringify({ slot_id: slot.id, test_code: slot.test_code }),
        });
      }
      setMessage(
        "Booked successfully. The confirmed visit is now in your record.",
      );
      await load();
    } catch (value) {
      setError(
        value instanceof Error ? value.message : "Unable to complete booking",
      );
    } finally {
      setBusy(null);
    }
  }

  const Icon = kind === "appointments" ? CalendarDays : FlaskConical;
  return (
    <>
      <PageHeading
        eyebrow="Real-time booking"
        title={kind === "appointments" ? "Book a doctor" : "Book a lab test"}
        description={
          kind === "appointments"
            ? "Choose an available clinician slot and pay the consultation fee in one flow."
            : "Choose an available test and laboratory slot."
        }
      />
      {kind === "appointments" ? (
        <Card className="mb-5">
          <CardContent className="pt-6">
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Reason for visit (shared securely with the clinician)"
              maxLength={500}
            />
          </CardContent>
        </Card>
      ) : null}
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
      <div className="grid gap-4 lg:grid-cols-2">
        {slots.map((slot) => {
          const amount = slot.fee_cents ?? slot.price_cents ?? 0;
          return (
            <Card key={slot.id}>
              <CardHeader>
                <div className="flex items-start gap-3">
                  <span className="grid size-10 place-items-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <div>
                    <CardTitle className="text-base">
                      {slot.provider ?? slot.test_name ?? slot.laboratory}
                    </CardTitle>
                    <CardDescription>
                      {slot.specialty ?? slot.laboratory} ·{" "}
                      {slot.location ?? "Online"}
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex items-center justify-between gap-3">
                <div className="text-sm">
                  <p className="font-medium">
                    {new Date(slot.starts_at).toLocaleString()}
                  </p>
                  <p className="text-muted-foreground">
                    {new Intl.NumberFormat("en-US", {
                      style: "currency",
                      currency: slot.currency,
                    }).format(amount / 100)}
                  </p>
                </div>
                <Button
                  disabled={busy === slot.id}
                  onClick={() => void book(slot)}
                >
                  {busy === slot.id ? "Booking…" : "Book"}
                </Button>
              </CardContent>
            </Card>
          );
        })}
      </div>
      {!slots.length && !error ? (
        <div className="grid place-items-center py-20 text-center text-muted-foreground">
          <CircleDashed className="mb-3 size-8" />
          <p>No matching slots are currently available.</p>
        </div>
      ) : null}
    </>
  );
}

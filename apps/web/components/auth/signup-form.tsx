"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AccountType } from "@healthos/api-types";
import { Button } from "@healthos/ui/button";
import { accountLabel, apiFetch } from "@/lib/auth";
import { FormError, FormField } from "./form-field";

interface MessageResponse {
  message: string;
  debug_code?: string | null;
  debug_mobile_code?: string | null;
}

export function SignupForm({
  accountType,
}: {
  accountType: Exclude<AccountType, "admin">;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(event.currentTarget);
    const common = {
      email: form.get("email"),
      password: form.get("password"),
      phone: form.get("phone"),
    };
    const payload =
      accountType === "patient" || accountType === "doctor"
        ? {
            ...common,
            first_name: form.get("first_name"),
            last_name: form.get("last_name"),
            ...(accountType === "patient"
              ? {
                  date_of_birth: form.get("date_of_birth") || null,
                  sex_at_birth: form.get("sex_at_birth") || null,
                  blood_type: form.get("blood_type") || null,
                  emergency_contact: form.get("emergency_contact") || null,
                }
              : {}),
            ...(accountType === "doctor"
              ? {
                  license_number: form.get("license_number"),
                  license_jurisdiction: form.get("license_jurisdiction"),
                  specialty: form.get("specialty"),
                  affiliation: form.get("affiliation"),
                }
              : {}),
          }
        : {
            ...common,
            legal_name: form.get("legal_name"),
            registration_number: form.get("registration_number"),
            license_number: form.get("license_number") || null,
            organization_type: form.get("organization_type"),
            product_types:
              accountType === "insurance"
                ? String(form.get("product_types") || "")
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean)
                : [],
          };
    try {
      const result = await apiFetch<MessageResponse>(
        `/api/v1/auth/signup/${accountType}`,
        {
          method: "POST",
          body: JSON.stringify(payload),
        },
      );
      if (result.debug_code)
        sessionStorage.setItem("healthos_debug_otp", result.debug_code);
      if (result.debug_mobile_code)
        sessionStorage.setItem(
          "healthos_debug_mobile_otp",
          result.debug_mobile_code,
        );
      router.push(
        `/verify-otp?email=${encodeURIComponent(String(common.email))}&account_type=${accountType}`,
      );
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to create account",
      );
    } finally {
      setPending(false);
    }
  }

  const person = accountType === "patient" || accountType === "doctor";
  return (
    <form onSubmit={submit} className="space-y-5">
      <FormError message={error} />
      {person ? (
        <div className="grid grid-cols-2 gap-3">
          <FormField
            label="First name"
            id="first_name"
            autoComplete="given-name"
            required
          />
          <FormField
            label="Last name"
            id="last_name"
            autoComplete="family-name"
            required
          />
        </div>
      ) : (
        <FormField label="Legal organization name" id="legal_name" required />
      )}
      {accountType === "doctor" ? (
        <div className="space-y-5">
          <FormField
            label="Medical license number"
            id="license_number"
            required
          />
          <FormField
            label="License jurisdiction"
            id="license_jurisdiction"
            required
          />
          <FormField label="Specialty" id="specialty" required />
          <FormField
            label="Hospital or practice affiliation"
            id="affiliation"
            required
          />
        </div>
      ) : null}
      {accountType === "hospital" || accountType === "insurance" ? (
        <div className="space-y-5">
          <FormField
            label="Registration number"
            id="registration_number"
            required
          />
          <FormField
            label={
              accountType === "hospital"
                ? "Facility license number"
                : "Company license number"
            }
            id="license_number"
            required
          />
          <FormField
            label={
              accountType === "hospital" ? "Facility type" : "Company type"
            }
            id="organization_type"
            required
          />
          {accountType === "insurance" ? (
            <FormField
              label="Insurance products (comma separated)"
              id="product_types"
              required
            />
          ) : null}
        </div>
      ) : null}
      {accountType === "patient" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField
            label="Date of birth"
            id="date_of_birth"
            type="date"
            required
          />
          <FormField label="Sex at birth" id="sex_at_birth" required />
          <FormField label="Blood type (if known)" id="blood_type" />
          <FormField
            label="Emergency contact"
            id="emergency_contact"
            required
          />
        </div>
      ) : null}
      <FormField
        label="Email address"
        id="email"
        type="email"
        autoComplete="email"
        required
      />
      <FormField
        label="Mobile number"
        id="phone"
        type="tel"
        autoComplete="tel"
        required
      />
      <FormField
        label="Password"
        id="password"
        type="password"
        autoComplete="new-password"
        minLength={12}
        maxLength={128}
        required
      />
      <p className="text-xs text-muted-foreground">
        Use at least 12 characters.
      </p>
      <Button className="w-full" type="submit" disabled={pending}>
        {pending
          ? "Creating account…"
          : `Create ${accountLabel(accountType)} account`}
      </Button>
      <p className="text-center text-sm text-muted-foreground">
        Already registered?{" "}
        <Link
          href={`/login/${accountType}`}
          className="text-primary hover:underline"
        >
          Sign in
        </Link>
      </p>
    </form>
  );
}

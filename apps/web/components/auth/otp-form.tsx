"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@healthos/ui/button";
import { apiFetch } from "@/lib/auth";
import { FormError, FormField } from "./form-field";

export function OtpForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialEmail = searchParams.get("email") ?? "";
  const accountType = searchParams.get("account_type") ?? "patient";
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [debugMobileCode, setDebugMobileCode] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setDebugCode(sessionStorage.getItem("healthos_debug_otp"));
    setDebugMobileCode(sessionStorage.getItem("healthos_debug_mobile_otp"));
    sessionStorage.removeItem("healthos_debug_otp");
    sessionStorage.removeItem("healthos_debug_mobile_otp");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch("/api/v1/auth/otp/verify", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          code: form.get("code"),
          purpose: "email_verification",
        }),
      });
      await apiFetch("/api/v1/auth/otp/verify", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          code: form.get("mobile_code"),
          purpose: "mobile_verification",
        }),
      });
      router.replace(`/login/${accountType}?verified=1`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Verification failed",
      );
    } finally {
      setPending(false);
    }
  }

  async function resend() {
    setError(null);
    try {
      const result = await apiFetch<{
        message: string;
        debug_code?: string | null;
      }>("/api/v1/auth/otp/resend", {
        method: "POST",
        body: JSON.stringify({
          email: initialEmail,
          purpose: "email_verification",
        }),
      });
      setMessage(result.message);
      setDebugCode(result.debug_code ?? null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to resend code",
      );
    }
  }

  async function resendMobile() {
    setError(null);
    try {
      const result = await apiFetch<{
        message: string;
        debug_code?: string | null;
      }>("/api/v1/auth/otp/resend", {
        method: "POST",
        body: JSON.stringify({
          email: initialEmail,
          purpose: "mobile_verification",
        }),
      });
      setMessage(result.message);
      setDebugMobileCode(result.debug_code ?? null);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to resend code",
      );
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <FormError message={error} />
      {message ? (
        <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
          {message}
        </p>
      ) : null}
      {debugCode ? (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
          Local development code: <strong>{debugCode}</strong>
        </p>
      ) : null}
      {debugMobileCode ? (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
          Local mobile code: <strong>{debugMobileCode}</strong>
        </p>
      ) : null}
      <FormField
        label="Email address"
        id="email"
        type="email"
        defaultValue={initialEmail}
        autoComplete="email"
        required
      />
      <FormField
        label="Email verification code"
        id="code"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]{6}"
        maxLength={6}
        required
      />
      <FormField
        label="Mobile verification code"
        id="mobile_code"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern="[0-9]{6}"
        maxLength={6}
        required
      />
      <Button type="submit" className="w-full" disabled={pending}>
        {pending ? "Verifying…" : "Verify email and mobile"}
      </Button>
      <Button type="button" variant="ghost" className="w-full" onClick={resend}>
        Send a new email code
      </Button>
      <Button
        type="button"
        variant="ghost"
        className="w-full"
        onClick={resendMobile}
      >
        Send a new mobile code
      </Button>
    </form>
  );
}

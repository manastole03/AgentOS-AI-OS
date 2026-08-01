"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@healthos/ui/button";
import { apiFetch } from "@/lib/auth";
import { FormError, FormField } from "./form-field";

export function ForgotPasswordForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const email = String(new FormData(event.currentTarget).get("email"));
    try {
      const result = await apiFetch<{ debug_code?: string | null }>(
        "/api/v1/auth/password/forgot",
        {
          method: "POST",
          body: JSON.stringify({ email }),
        },
      );
      if (result.debug_code)
        sessionStorage.setItem("healthos_debug_otp", result.debug_code);
      router.push(`/reset-password?email=${encodeURIComponent(email)}`);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to request a reset",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <FormError message={error} />
      <FormField
        label="Email address"
        id="email"
        type="email"
        autoComplete="email"
        required
      />
      <Button className="w-full" type="submit" disabled={pending}>
        {pending ? "Sending…" : "Send reset code"}
      </Button>
      <Link
        href="/login/patient"
        className="block text-center text-sm text-primary hover:underline"
      >
        Return to sign in
      </Link>
    </form>
  );
}

"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@healthos/ui/button";
import { apiFetch } from "@/lib/auth";
import { FormError, FormField } from "./form-field";

export function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [debugCode, setDebugCode] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    setDebugCode(sessionStorage.getItem("healthos_debug_otp"));
    sessionStorage.removeItem("healthos_debug_otp");
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password"));
    if (password !== String(form.get("password_confirm"))) {
      setError("Passwords do not match");
      setPending(false);
      return;
    }
    try {
      await apiFetch("/api/v1/auth/password/reset", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          code: form.get("code"),
          password,
        }),
      });
      router.replace("/login?reset=1");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to reset password",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <FormError message={error} />
      {debugCode ? (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-800">
          Local development code: <strong>{debugCode}</strong>
        </p>
      ) : null}
      <FormField
        label="Email address"
        id="email"
        type="email"
        defaultValue={searchParams.get("email") ?? ""}
        required
      />
      <FormField
        label="Reset code"
        id="code"
        inputMode="numeric"
        pattern="[0-9]{6}"
        maxLength={6}
        required
      />
      <FormField
        label="New password"
        id="password"
        type="password"
        minLength={12}
        maxLength={128}
        required
      />
      <FormField
        label="Confirm password"
        id="password_confirm"
        type="password"
        minLength={12}
        required
      />
      <Button className="w-full" type="submit" disabled={pending}>
        {pending ? "Resetting…" : "Reset password"}
      </Button>
    </form>
  );
}

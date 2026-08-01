"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AccountType, AuthResponse } from "@healthos/api-types";
import { Button } from "@healthos/ui/button";
import { accountLabel, apiFetch } from "@/lib/auth";
import { env } from "@/lib/env";
import { FormError, FormField } from "./form-field";

export function LoginForm({ accountType }: { accountType: AccountType }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    const form = new FormData(event.currentTarget);
    try {
      await apiFetch<AuthResponse>(`/api/v1/auth/login/${accountType}`, {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      router.replace("/dashboard");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to sign in");
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
      <FormField
        label="Password"
        id="password"
        type="password"
        autoComplete="current-password"
        minLength={12}
        required
      />
      <div className="flex justify-end">
        <Link
          href="/forgot-password"
          className="text-sm text-primary hover:underline"
        >
          Forgot password?
        </Link>
      </div>
      <Button className="w-full" type="submit" disabled={pending}>
        {pending ? "Signing in…" : `Sign in as ${accountLabel(accountType)}`}
      </Button>
      {accountType !== "admin" ? (
        <>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" /> or{" "}
            <span className="h-px flex-1 bg-border" />
          </div>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={() =>
              window.location.assign(
                `${env.NEXT_PUBLIC_API_URL}/api/v1/auth/google/${accountType}`,
              )
            }
          >
            Continue with Google
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            New to HealthOS?{" "}
            <Link
              href={`/signup/${accountType}`}
              className="text-primary hover:underline"
            >
              Create an account
            </Link>
          </p>
        </>
      ) : null}
    </form>
  );
}

"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import type { ProfileResponse } from "@healthos/api-types";
import { Button } from "@healthos/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { authenticatedFetch } from "@/lib/auth";
import { FormError, FormField } from "./form-field";

export function ProfileForm() {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const load = useCallback(async () => {
    try {
      setProfile(await authenticatedFetch<ProfileResponse>("/api/v1/users/me"));
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to load profile",
      );
    }
  }, []);
  useEffect(() => void load(), [load]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    setMessage(null);
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(
      ["first_name", "last_name", "legal_name", "phone", "avatar_url"]
        .map((field) => [field, form.get(field)])
        .filter(([, value]) => value !== null && value !== ""),
    );
    try {
      setProfile(
        await authenticatedFetch<ProfileResponse>("/api/v1/users/me", {
          method: "PATCH",
          body: JSON.stringify(payload),
        }),
      );
      setMessage("Profile updated.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to update profile",
      );
    } finally {
      setPending(false);
    }
  }

  if (!profile)
    return <p className="text-sm text-muted-foreground">Loading profile…</p>;
  const person =
    profile.account_type === "patient" || profile.account_type === "doctor";
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>
          Identity fields such as licenses and registration numbers cannot be
          edited here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={submit}>
          <FormError message={error} />
          {message ? (
            <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-700">
              {message}
            </p>
          ) : null}
          {person ? (
            <div className="grid grid-cols-2 gap-3">
              <FormField
                label="First name"
                id="first_name"
                defaultValue={profile.first_name ?? ""}
              />
              <FormField
                label="Last name"
                id="last_name"
                defaultValue={profile.last_name ?? ""}
              />
            </div>
          ) : null}
          {profile.legal_name !== null && profile.legal_name !== undefined ? (
            <FormField
              label="Legal name"
              id="legal_name"
              defaultValue={profile.legal_name}
            />
          ) : null}
          <FormField
            label="Phone"
            id="phone"
            type="tel"
            defaultValue={profile.phone ?? ""}
          />
          <FormField
            label="Avatar URL"
            id="avatar_url"
            type="url"
            defaultValue={profile.avatar_url ?? ""}
          />
          <Button type="submit" disabled={pending}>
            {pending ? "Saving…" : "Save profile"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

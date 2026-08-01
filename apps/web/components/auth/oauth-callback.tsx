"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/auth";

export function OAuthCallback() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState("Completing secure sign in…");

  useEffect(() => {
    if (searchParams.get("error")) {
      setMessage(
        "Google sign in could not be completed. Return to the appropriate login page.",
      );
      return;
    }
    apiFetch("/api/v1/auth/session")
      .then(() => {
        router.replace("/dashboard");
        router.refresh();
      })
      .catch(() =>
        setMessage(
          "Your session could not be established. Please sign in again.",
        ),
      );
  }, [router, searchParams]);

  return <p className="text-sm text-muted-foreground">{message}</p>;
}

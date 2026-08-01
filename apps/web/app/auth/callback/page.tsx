import { Suspense } from "react";
import { AuthShell } from "@/components/auth/auth-shell";
import { OAuthCallback } from "@/components/auth/oauth-callback";

export default function OAuthCallbackPage() {
  return (
    <AuthShell
      title="Google sign in"
      description="HealthOS is validating your identity and session."
    >
      <Suspense
        fallback={
          <p className="text-sm text-muted-foreground">
            Completing secure sign in…
          </p>
        }
      >
        <OAuthCallback />
      </Suspense>
    </AuthShell>
  );
}

import { Suspense } from "react";
import { AuthShell } from "@/components/auth/auth-shell";
import { OtpForm } from "@/components/auth/otp-form";

export default function VerifyOtpPage() {
  return (
    <AuthShell
      title="Verify your email"
      description="Enter the six-digit code sent to your email address."
    >
      <Suspense
        fallback={
          <p className="text-sm text-muted-foreground">Loading verification…</p>
        }
      >
        <OtpForm />
      </Suspense>
    </AuthShell>
  );
}

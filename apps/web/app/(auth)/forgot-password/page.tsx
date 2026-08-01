import { AuthShell } from "@/components/auth/auth-shell";
import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";

export default function ForgotPasswordPage() {
  return (
    <AuthShell
      title="Reset your password"
      description="We will send a time-limited reset code if the account exists."
    >
      <ForgotPasswordForm />
    </AuthShell>
  );
}

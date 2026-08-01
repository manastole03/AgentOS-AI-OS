import { AccountChooser } from "@/components/auth/account-chooser";
import { AuthShell } from "@/components/auth/auth-shell";
import { publicSignupTypes } from "@/lib/auth";

export default function SignupChooserPage() {
  return (
    <AuthShell
      title="Create your account"
      description="Select the identity type that matches how you will use HealthOS."
    >
      <AccountChooser mode="signup" types={publicSignupTypes} />
    </AuthShell>
  );
}

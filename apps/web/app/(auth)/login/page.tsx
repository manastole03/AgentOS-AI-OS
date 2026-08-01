import { AccountChooser } from "@/components/auth/account-chooser";
import { AuthShell } from "@/components/auth/auth-shell";
import { accountTypes } from "@/lib/auth";

export default function LoginChooserPage() {
  return (
    <AuthShell
      title="Choose your account"
      description="HealthOS applies the authorization policy for the selected account type."
    >
      <AccountChooser mode="login" types={accountTypes} />
    </AuthShell>
  );
}

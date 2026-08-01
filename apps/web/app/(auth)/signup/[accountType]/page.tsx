import { notFound } from "next/navigation";
import type { AccountType } from "@healthos/api-types";
import { AuthShell } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/auth/signup-form";
import { accountLabel, isAccountType, publicSignupTypes } from "@/lib/auth";

export function generateStaticParams() {
  return publicSignupTypes.map((accountType) => ({ accountType }));
}

export default async function SignupPage({
  params,
}: {
  params: Promise<{ accountType: string }>;
}) {
  const { accountType } = await params;
  if (!isAccountType(accountType) || accountType === "admin") notFound();
  const type = accountType as Exclude<AccountType, "admin">;
  return (
    <AuthShell
      title={`Create a ${accountLabel(type)} account`}
      description="Your email must be verified before the account can sign in."
    >
      <SignupForm accountType={type} />
    </AuthShell>
  );
}

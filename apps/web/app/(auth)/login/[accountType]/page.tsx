import { notFound } from "next/navigation";
import type { AccountType } from "@healthos/api-types";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";
import { accountLabel, accountTypes, isAccountType } from "@/lib/auth";

export function generateStaticParams() {
  return accountTypes.map((accountType) => ({ accountType }));
}

export default async function LoginPage({
  params,
}: {
  params: Promise<{ accountType: string }>;
}) {
  const { accountType } = await params;
  if (!isAccountType(accountType)) notFound();
  const type: AccountType = accountType;
  return (
    <AuthShell
      title={`${accountLabel(type)} sign in`}
      description="Use your verified HealthOS account to continue."
    >
      <LoginForm accountType={type} />
    </AuthShell>
  );
}

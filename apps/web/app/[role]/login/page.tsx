import { notFound } from "next/navigation";
import type { AccountType } from "@healthos/api-types";
import { AuthShell } from "@/components/auth/auth-shell";
import { LoginForm } from "@/components/auth/login-form";
import { accountLabel } from "@/lib/auth";

const roles: Record<string, AccountType> = {
  patient: "patient",
  doctors: "doctor",
  hospital: "hospital",
  insurance: "insurance",
  admin: "admin",
};
export function generateStaticParams() {
  return Object.keys(roles).map((role) => ({ role }));
}
export default async function RoleLogin({
  params,
}: {
  params: Promise<{ role: string }>;
}) {
  const { role } = await params;
  const accountType = roles[role];
  if (!accountType) notFound();
  return (
    <AuthShell
      title={`${accountLabel(accountType)} sign in`}
      description={`Secure access to the ${accountLabel(accountType)} workspace.`}
    >
      <LoginForm accountType={accountType} />
    </AuthShell>
  );
}

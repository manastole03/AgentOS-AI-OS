import { notFound } from "next/navigation";
import type { AccountType } from "@healthos/api-types";
import { AuthShell } from "@/components/auth/auth-shell";
import { SignupForm } from "@/components/auth/signup-form";
import { accountLabel } from "@/lib/auth";
import Link from "next/link";
import { Button } from "@healthos/ui/button";

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
export default async function RoleSignup({
  params,
}: {
  params: Promise<{ role: string }>;
}) {
  const { role } = await params;
  const accountType = roles[role];
  if (!accountType) notFound();
  if (accountType === "admin")
    return (
      <AuthShell
        title="Administrator access"
        description="Administrator accounts are provisioned by an authorized platform operator and cannot be self-registered."
      >
        <Button className="w-full" asChild>
          <Link href="/admin/login">Sign in with a provisioned account</Link>
        </Button>
      </AuthShell>
    );
  return (
    <AuthShell
      title={`Create a ${accountLabel(accountType)} account`}
      description="Complete role verification, then verify both email and mobile number."
    >
      <SignupForm accountType={accountType} />
    </AuthShell>
  );
}

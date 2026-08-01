import { notFound } from "next/navigation";
import { RoleLanding, landingRoutes } from "@/components/marketing/role-landing";

/**
 * `insurance` and `admin` are left out of prerendering: a static `/insurance`
 * and `/admin` page exists for the signed-in workspaces and wins the match, so
 * the middleware rewrites signed-out requests to `/landing/<role>` instead.
 */
export function generateStaticParams() {
  return Object.keys(landingRoutes)
    .filter((role) => role !== "insurance" && role !== "admin")
    .map((role) => ({ role }));
}

export default async function RolePage({
  params,
}: {
  params: Promise<{ role: string }>;
}) {
  const { role } = await params;
  const accountType = landingRoutes[role];
  if (!accountType) notFound();
  return <RoleLanding accountType={accountType} route={role} />;
}

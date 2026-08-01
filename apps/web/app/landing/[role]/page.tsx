import { notFound } from "next/navigation";
import { RoleLanding, landingRoutes } from "@/components/marketing/role-landing";

/**
 * Internal target for the two landing pages a signed-in workspace shadows.
 *
 * `/insurance` and `/admin` resolve to the protected workspaces because a
 * static segment outranks `app/[role]`. The middleware rewrites the signed-out
 * request here, so the public URL is unchanged and the marketing page still
 * renders.
 */

export function generateStaticParams() {
  return [{ role: "insurance" }, { role: "admin" }];
}

export default async function ShadowedRoleLandingPage({
  params,
}: {
  params: Promise<{ role: string }>;
}) {
  const { role } = await params;
  const accountType = landingRoutes[role];
  if (!accountType) notFound();
  return <RoleLanding accountType={accountType} route={role} />;
}

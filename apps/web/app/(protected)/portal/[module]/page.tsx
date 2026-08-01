import { ModuleWorkspace } from "@/components/portal/module-workspace";

export default async function PortalModulePage({
  params,
}: {
  params: Promise<{ module: string }>;
}) {
  const { module } = await params;
  return <ModuleWorkspace slug={module} />;
}

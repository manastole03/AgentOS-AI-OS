import type { Metadata } from "next";
import { HealthWorkspace } from "@/components/health/health-workspace";

export const metadata: Metadata = {
  title: "Health record",
  description: "Conditions, allergies, immunizations, and vital trends.",
};

export default function HealthPage() {
  return <HealthWorkspace />;
}

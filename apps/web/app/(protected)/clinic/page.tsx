import type { Metadata } from "next";
import { ClinicWorkspace } from "@/components/clinic/clinic-workspace";

export const metadata: Metadata = {
  title: "Clinical workspace",
  description:
    "Today's schedule, patient records, documentation, coding, referrals, and availability.",
};

export default function ClinicPage() {
  return <ClinicWorkspace />;
}

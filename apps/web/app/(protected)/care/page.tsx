import type { Metadata } from "next";
import { CareWorkspace } from "@/components/care/care-workspace";

export const metadata: Metadata = {
  title: "Care & medications",
  description:
    "Appointments, medication courses, reminders, and lab orders in one place.",
};

export default function CarePage() {
  return <CareWorkspace />;
}

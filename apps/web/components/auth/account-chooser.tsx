import Link from "next/link";
import type { AccountType } from "@healthos/api-types";
import {
  Building2,
  CircleUserRound,
  HeartHandshake,
  Shield,
  Stethoscope,
  ArrowRight,
} from "lucide-react";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@healthos/ui/card";
import { accountLabel } from "@/lib/auth";

const icons = {
  patient: CircleUserRound,
  doctor: Stethoscope,
  hospital: Building2,
  insurance: HeartHandshake,
  admin: Shield,
};

const descriptions: Record<AccountType, string> = {
  patient: "Manage your personal care and coverage",
  doctor: "Access your clinical workspace",
  hospital: "Coordinate facility operations",
  insurance: "Manage plans, claims, and members",
  admin: "Manage the HealthOS platform",
};

export function AccountChooser({
  mode,
  types,
}: {
  mode: "login" | "signup";
  types: AccountType[];
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {types.map((type) => {
        const Icon = icons[type];
        return (
          <Link href={`/${mode}/${type}`} key={type} className="group rounded-xl">
            <Card className="h-full transition duration-200 group-hover:-translate-y-0.5 group-hover:border-primary/40 group-hover:shadow-md">
              <CardHeader className="p-5">
                <div className="flex items-start justify-between">
                  <span className="grid size-10 place-items-center rounded-xl bg-primary/10 text-primary"><Icon className="size-5" /></span>
                  <ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-1 group-hover:text-primary" />
                </div>
                <CardTitle className="pt-2 text-base">{accountLabel(type)}</CardTitle>
                <CardDescription className="leading-5">{descriptions[type]}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}

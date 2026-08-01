import type { AccountType } from "@healthos/api-types";

/**
 * Role-aware routing table for the workspace surfaces.
 *
 * This module is deliberately dependency-free (no icons, no React) because the
 * edge middleware imports it. `lib/portal.ts` decorates the same table with
 * presentation for the sidebar.
 */

export const accountTypes = [
  "patient",
  "doctor",
  "hospital",
  "insurance",
  "admin",
] as const satisfies readonly AccountType[];

export function isAccountType(value: string): value is AccountType {
  return (accountTypes as readonly string[]).includes(value);
}

export interface WorkspaceRoute {
  href: string;
  label: string;
  description: string;
  /** Account types allowed to open the route. */
  roles: readonly AccountType[];
}

/**
 * Every workspace destination, longest paths first so prefix matching in the
 * middleware resolves `/care/anything` to `/care` and never to `/`.
 */
export const workspaceRoutes: readonly WorkspaceRoute[] = [
  {
    href: "/health",
    label: "Health record",
    description: "Conditions, allergies, immunizations, and vital trends",
    roles: ["patient"],
  },
  {
    href: "/care",
    label: "Care & medications",
    description: "Appointments, medication courses, reminders, and lab orders",
    roles: ["patient"],
  },
  {
    href: "/insurance",
    label: "Coverage",
    description: "Policies, claims, loyalty points, and the plan marketplace",
    roles: ["patient"],
  },
  {
    href: "/clinic",
    label: "Clinical workspace",
    description: "Schedule, critical results, and referral coordination",
    roles: ["doctor"],
  },
  {
    href: "/operations",
    label: "Operations",
    description: "Departments, practitioners, services, and revenue cycle",
    roles: ["hospital"],
  },
  {
    href: "/payer",
    label: "Payer operations",
    description: "Claims, prior authorization, and plan performance",
    roles: ["insurance"],
  },
  {
    href: "/admin",
    label: "Platform control",
    description: "Adoption, PHI access, support, and privacy requests",
    roles: ["admin"],
  },
];

/** Where a role lands after sign-in, and where a denied navigation goes. */
export const roleHome: Record<AccountType, string> = {
  patient: "/health",
  doctor: "/clinic",
  hospital: "/operations",
  insurance: "/payer",
  admin: "/admin",
};

/** Routes every signed-in account may open, whatever its role. */
export const sharedProtectedPrefixes = [
  "/dashboard",
  "/profile",
  "/portal",
] as const;

export function workspaceRoutesFor(
  accountType: AccountType,
): WorkspaceRoute[] {
  return workspaceRoutes.filter((item) => item.roles.includes(accountType));
}

function matchesPrefix(pathname: string, prefix: string): boolean {
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** The workspace route that owns a pathname, or null when none does. */
export function workspaceRouteFor(pathname: string): WorkspaceRoute | null {
  return (
    workspaceRoutes.find((item) => matchesPrefix(pathname, item.href)) ?? null
  );
}

export function isSharedProtectedPath(pathname: string): boolean {
  return sharedProtectedPrefixes.some((prefix) =>
    matchesPrefix(pathname, prefix),
  );
}

export function isProtectedPath(pathname: string): boolean {
  return isSharedProtectedPath(pathname) || workspaceRouteFor(pathname) !== null;
}

/**
 * `/insurance` and `/admin` are both a public role landing page and a signed-in
 * workspace. A static segment wins over `app/[role]`, so the signed-out view is
 * served by rewriting to the landing route instead.
 */
export const landingShadowedRoutes: Record<string, string> = {
  "/insurance": "/landing/insurance",
  "/admin": "/landing/admin",
};

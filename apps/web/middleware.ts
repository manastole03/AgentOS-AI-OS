import { NextResponse, type NextRequest } from "next/server";
import type { AccountType } from "@healthos/api-types";
import {
  isAccountType,
  isProtectedPath,
  landingShadowedRoutes,
  roleHome,
  workspaceRouteFor,
} from "@/lib/role-routes";

/**
 * Navigation-level access control.
 *
 * The access cookie is read, never verified: this middleware decides which
 * screen to *show*, and the API remains the only authority on what data an
 * account may read. An unreadable or expired token therefore falls through to
 * the page, where the client refreshes the session or is bounced to login.
 */

function decodeRoles(token: string | undefined): string[] {
  if (!token) return [];
  const payload = token.split(".")[1];
  if (!payload) return [];
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const claims = JSON.parse(json) as { roles?: unknown };
    return Array.isArray(claims.roles) ? claims.roles.map(String) : [];
  } catch {
    return [];
  }
}

/** The account type behind the session, when the token states one. */
function sessionAccountType(request: NextRequest): AccountType | null {
  const roles = decodeRoles(request.cookies.get("healthos_access")?.value);
  return roles.find(isAccountType) ?? null;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!isProtectedPath(pathname)) return NextResponse.next();

  const hasSession =
    request.cookies.has("healthos_access") ||
    request.cookies.has("healthos_refresh");

  if (!hasSession) {
    const landing = landingShadowedRoutes[pathname];
    if (landing) {
      return NextResponse.rewrite(new URL(landing, request.url));
    }
    const loginUrl = new URL("/login/patient", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  const workspace = workspaceRouteFor(pathname);
  if (!workspace) return NextResponse.next();

  const accountType = sessionAccountType(request);
  if (!accountType) return NextResponse.next();
  if (workspace.roles.includes(accountType)) return NextResponse.next();

  // Wrong role for this workspace: send the account to its own home rather
  // than showing an error it cannot act on.
  return NextResponse.redirect(new URL(roleHome[accountType], request.url));
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/profile/:path*",
    "/portal/:path*",
    "/health/:path*",
    "/care/:path*",
    "/insurance/:path*",
    "/clinic/:path*",
    "/operations/:path*",
    "/payer/:path*",
    "/admin/:path*",
  ],
};

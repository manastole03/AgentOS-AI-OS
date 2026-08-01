"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { AppManifest, UserSummary } from "@healthos/api-types";
import { Badge } from "@healthos/ui/badge";
import { Button } from "@healthos/ui/button";
import {
  SidebarNav,
  type RenderSidebarNavLink,
  type SidebarNavItem,
} from "@healthos/ui/sidebar-nav";
import { ThemeToggle } from "@healthos/ui/theme-toggle";
import { cn } from "@healthos/utils";
import { Bell, HeartPulse, Menu, Search, X } from "lucide-react";
import { authenticatedFetch } from "@/lib/auth";
import { dashboardModule, roleMeta, roleWorkspaces } from "@/lib/portal";
import { manifestModules } from "@/lib/app-manifest";
import { LogoutButton } from "@/components/layout/logout-button";

interface ShellDestination extends SidebarNavItem {
  description: string;
}

export function PortalShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [user, setUser] = useState<UserSummary | null>(null);
  const [manifest, setManifest] = useState<AppManifest | null>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    Promise.all([
      authenticatedFetch<UserSummary>("/api/v1/auth/session"),
      authenticatedFetch<AppManifest>("/api/v1/app-manifest"),
    ])
      .then(([session, application]) => {
        setUser(session);
        setManifest(application);
      })
      .catch(() => undefined);
  }, []);

  const workspaces = useMemo<ShellDestination[]>(() => {
    const items = user ? roleWorkspaces[user.account_type] : [];
    return [
      {
        href: "/dashboard",
        label: dashboardModule.label,
        description: dashboardModule.description,
        icon: dashboardModule.icon,
      },
      ...items.map((item) => ({
        href: item.href,
        label: item.label,
        description: item.description,
        icon: item.icon,
      })),
    ];
  }, [user]);

  const modules = useMemo<ShellDestination[]>(
    () =>
      (manifest ? manifestModules(manifest) : []).map((item) => ({
        href: `/portal/${item.slug}`,
        label: item.label,
        description: item.description,
        icon: item.icon,
      })),
    [manifest],
  );

  const needle = query.trim().toLowerCase();
  const matches = (item: ShellDestination) =>
    !needle || item.label.toLowerCase().includes(needle);
  const visibleWorkspaces = workspaces.filter(matches);
  const visibleModules = modules.filter(matches);
  const hasResults = visibleWorkspaces.length + visibleModules.length > 0;

  // Longest match wins, so /portal/vitals never resolves to /portal.
  const activeHref = [...workspaces, ...modules]
    .map((item) => item.href)
    .filter(
      (href) => pathname === href || pathname.startsWith(`${href}/`),
    )
    .sort((a, b) => b.length - a.length)[0];

  const current = [...workspaces, ...modules].find(
    (item) => item.href === activeHref,
  );
  const meta = user ? roleMeta[user.account_type] : null;

  const renderLink: RenderSidebarNavLink = ({ item, linkProps, children }) => (
    <Link {...linkProps} key={item.href} onClick={() => setOpen(false)}>
      {children}
    </Link>
  );

  return (
    <div className="min-h-screen bg-muted/20">
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-transform lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex h-20 items-center justify-between border-b border-sidebar-border px-6">
          <Link
            href="/dashboard"
            className="flex items-center gap-3"
            onClick={() => setOpen(false)}
          >
            <span className="grid size-10 place-items-center rounded-xl bg-sidebar-primary text-sidebar-primary-foreground">
              <HeartPulse className="size-6" aria-hidden="true" />
            </span>
            <span>
              <strong className="block text-lg">HealthOS</strong>
              <span className="text-xs text-sidebar-foreground/60">
                {meta?.accent ?? "Secure workspace"}
              </span>
            </span>
          </Link>
          <button
            type="button"
            className="lg:hidden"
            onClick={() => setOpen(false)}
            aria-label="Close navigation"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>

        <div className="border-b border-sidebar-border px-5 py-5">
          <p className="text-xs uppercase tracking-[0.2em] text-sidebar-foreground/60">
            Workspace
          </p>
          <div className="mt-2 flex items-center gap-2 text-sm font-medium">
            {meta ? (
              <meta.icon
                className="size-4 text-sidebar-primary"
                aria-hidden="true"
              />
            ) : null}
            {meta?.label ?? "Loading portal"}
          </div>
          <label className="relative mt-4 block">
            <Search
              className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-sidebar-foreground/50"
              aria-hidden="true"
            />
            <span className="sr-only">Find a tool</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a tool…"
              className="h-10 w-full rounded-lg border border-sidebar-border bg-sidebar-accent/40 pl-9 pr-3 text-sm text-sidebar-foreground placeholder:text-sidebar-foreground/50 focus:border-sidebar-ring focus:outline-none"
            />
          </label>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
          {visibleWorkspaces.length ? (
            <SidebarNav
              groupLabel="Workspaces"
              items={visibleWorkspaces}
              activeHref={activeHref}
              renderLink={renderLink}
            />
          ) : null}
          {visibleModules.length ? (
            <SidebarNav
              groupLabel="Tools"
              items={visibleModules}
              activeHref={activeHref}
              renderLink={renderLink}
            />
          ) : null}
          {needle && !hasResults ? (
            <p className="px-3 py-6 text-center text-sm text-sidebar-foreground/60">
              No tools match “{query}”
            </p>
          ) : null}
        </div>

        <div className="border-t border-sidebar-border p-4">
          <Link
            href="/profile"
            className="mb-3 block rounded-lg bg-sidebar-accent/40 p-3 hover:bg-sidebar-accent"
            onClick={() => setOpen(false)}
          >
            <p className="truncate text-sm font-medium">
              {user?.email ?? "Loading account…"}
            </p>
            <p className="mt-1 text-xs capitalize text-sidebar-foreground/60">
              {user?.account_type ?? "Secure session"}
            </p>
          </Link>
          <LogoutButton />
        </div>
      </aside>

      {open ? (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setOpen(false)}
          aria-label="Close menu"
        />
      ) : null}

      <div className="lg:pl-72">
        <header className="sticky top-0 z-30 flex h-20 items-center gap-3 border-b bg-background/90 px-4 backdrop-blur-xl md:px-8">
          <Button
            variant="outline"
            size="sm"
            className="lg:hidden"
            onClick={() => setOpen(true)}
            aria-label="Open navigation"
          >
            <Menu className="size-4" aria-hidden="true" />
          </Button>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">
              {current?.label ?? "Your workspace"}
            </p>
            <p className="hidden truncate text-xs text-muted-foreground sm:block">
              {current?.description ?? "Secure care operations"}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              className="relative rounded-full"
              asChild
            >
              <Link href="/portal/notifications" aria-label="View notifications">
                <Bell className="size-4" aria-hidden="true" />
                <span
                  className="absolute right-1 top-1 size-2 rounded-full bg-critical ring-2 ring-background"
                  aria-hidden="true"
                />
              </Link>
            </Button>
            <ThemeToggle className="size-9" />
            {user ? (
              <Badge variant="secondary" className="capitalize">
                {user.account_type}
              </Badge>
            ) : null}
          </div>
        </header>
        <main className="p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}

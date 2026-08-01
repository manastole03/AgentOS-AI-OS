"use client";

import * as React from "react";
import { cn } from "@healthos/utils";

export interface SidebarNavItem {
  /** Destination passed straight through to the rendered link. */
  href: string;
  label: string;
  /** Icon component, e.g. a `lucide-react` icon. */
  icon?: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  /** Trailing count or short status text. */
  badge?: React.ReactNode;
}

export interface SidebarNavLinkRenderProps {
  item: SidebarNavItem;
  isActive: boolean;
  /**
   * Spread onto the router link element. Contains the resolved className and
   * `aria-current="page"` for the active item.
   */
  linkProps: {
    href: string;
    className: string;
    "aria-current"?: "page";
  };
  /** Icon, label and badge content. */
  children: React.ReactNode;
}

export type RenderSidebarNavLink = (
  props: SidebarNavLinkRenderProps,
) => React.ReactNode;

export interface SidebarNavProps extends Omit<
  React.HTMLAttributes<HTMLElement>,
  "children"
> {
  items: SidebarNavItem[];
  /** `href` of the item that represents the current page. */
  activeHref?: string;
  /** Visible heading for the group; also names the nav landmark. */
  groupLabel?: string;
  /**
   * Accessible name for the nav landmark. Defaults to `groupLabel`, then
   * "Sidebar". Only used when `groupLabel` is absent.
   */
  ariaLabel?: string;
  /**
   * Supply the app's router link (e.g. `next/link`). Defaults to an `<a>`.
   * This package intentionally has no knowledge of the router.
   */
  renderLink?: RenderSidebarNavLink;
}

const itemClassName =
  "group relative flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground/80 outline-none transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar";

const activeItemClassName =
  "bg-sidebar-accent font-medium text-sidebar-accent-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground";

const defaultRenderLink: RenderSidebarNavLink = ({ linkProps, children }) => (
  <a {...linkProps}>{children}</a>
);

const SidebarNav = React.forwardRef<HTMLElement, SidebarNavProps>(
  (
    {
      className,
      items,
      activeHref,
      groupLabel,
      ariaLabel,
      renderLink = defaultRenderLink,
      ...props
    },
    ref,
  ) => {
    const groupLabelId = React.useId();

    return (
      <nav
        ref={ref}
        aria-label={groupLabel ? undefined : (ariaLabel ?? "Sidebar")}
        aria-labelledby={groupLabel ? groupLabelId : undefined}
        className={cn("flex flex-col gap-2", className)}
        {...props}
      >
        {groupLabel ? (
          <h2
            id={groupLabelId}
            className="px-3 pt-1 text-xs font-semibold uppercase tracking-wide text-sidebar-foreground/60"
          >
            {groupLabel}
          </h2>
        ) : null}
        <ul className="flex list-none flex-col gap-1">
          {items.map((item) => {
            const isActive = item.href === activeHref;
            const Icon = item.icon;

            return (
              <li key={item.href}>
                {renderLink({
                  item,
                  isActive,
                  linkProps: {
                    href: item.href,
                    className: cn(
                      itemClassName,
                      isActive && activeItemClassName,
                    ),
                    ...(isActive ? { "aria-current": "page" as const } : {}),
                  },
                  children: (
                    <>
                      <span
                        aria-hidden="true"
                        className={cn(
                          "absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-sidebar-primary transition-opacity",
                          isActive ? "opacity-100" : "opacity-0",
                        )}
                      />
                      {Icon ? (
                        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      ) : null}
                      <span className="min-w-0 flex-1 truncate">
                        {item.label}
                      </span>
                      {item.badge !== undefined && item.badge !== null ? (
                        <span className="tabular ml-auto inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-sidebar-primary px-1.5 text-[0.6875rem] font-semibold leading-none text-sidebar-primary-foreground">
                          {item.badge}
                        </span>
                      ) : null}
                    </>
                  ),
                })}
              </li>
            );
          })}
        </ul>
      </nav>
    );
  },
);
SidebarNav.displayName = "SidebarNav";

export { SidebarNav };

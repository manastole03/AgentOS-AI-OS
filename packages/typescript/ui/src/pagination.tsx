"use client";

import * as React from "react";
import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { cn } from "@healthos/utils";
import { Button } from "./button";

function range(start: number, end: number): number[] {
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

/**
 * Build the visible page list: always the first and last page, `siblingCount`
 * pages either side of the current one, and `"ellipsis"` where pages are
 * skipped. The slot count is stable so the control never reflows as you page.
 */
export function getPaginationRange(
  page: number,
  pageCount: number,
  siblingCount = 1,
): Array<number | "ellipsis"> {
  const totalPages = Math.max(0, Math.floor(pageCount));
  if (totalPages === 0) return [];

  const siblings = Math.max(0, Math.floor(siblingCount));
  const current = Math.min(Math.max(1, Math.floor(page)), totalPages);

  // first + last + current + siblings on both sides + two ellipsis slots
  const maxSlots = siblings * 2 + 5;
  if (totalPages <= maxSlots) return range(1, totalPages);

  const leftSibling = Math.max(current - siblings, 1);
  const rightSibling = Math.min(current + siblings, totalPages);
  const showLeftEllipsis = leftSibling > 2;
  const showRightEllipsis = rightSibling < totalPages - 1;

  if (!showLeftEllipsis && showRightEllipsis) {
    return [...range(1, siblings * 2 + 3), "ellipsis", totalPages];
  }

  if (showLeftEllipsis && !showRightEllipsis) {
    return [
      1,
      "ellipsis",
      ...range(totalPages - (siblings * 2 + 2), totalPages),
    ];
  }

  return [
    1,
    "ellipsis",
    ...range(leftSibling, rightSibling),
    "ellipsis",
    totalPages,
  ];
}

const iconButtonClassName = "size-9 p-0";

export interface PaginationProps extends Omit<
  React.HTMLAttributes<HTMLElement>,
  "onChange"
> {
  /** Current page, 1-based. */
  page: number;
  /** Total number of pages. A value of 0 or 1 still renders a stable control. */
  pageCount: number;
  /** Called with a clamped, 1-based page number. */
  onPageChange: (page: number) => void;
  /** Pages shown either side of the current page. */
  siblingCount?: number;
  /** Render first/last jump buttons. */
  showEdgeButtons?: boolean;
  /** Current rows-per-page value. Required to render the page-size select. */
  pageSize?: number;
  /** Rows-per-page choices. The select only renders with `onPageSizeChange`. */
  pageSizeOptions?: number[];
  onPageSizeChange?: (pageSize: number) => void;
  /** Disable the whole control, e.g. while a page is loading. */
  disabled?: boolean;
  /** Accessible name for the nav landmark. */
  label?: string;
  /**
   * Text pushed to the polite live region after a page change. Override it to
   * announce row counts alongside the page number.
   */
  statusText?: string;
}

const Pagination = React.forwardRef<HTMLElement, PaginationProps>(
  (
    {
      className,
      page,
      pageCount,
      onPageChange,
      siblingCount = 1,
      showEdgeButtons = true,
      pageSize,
      pageSizeOptions = [10, 25, 50, 100],
      onPageSizeChange,
      disabled = false,
      label = "Pagination",
      statusText,
      ...props
    },
    ref,
  ) => {
    const reactId = React.useId();
    const totalPages = Math.max(1, Math.floor(pageCount) || 1);
    const currentPage = Math.min(
      Math.max(1, Math.floor(page) || 1),
      totalPages,
    );
    const pages = getPaginationRange(currentPage, totalPages, siblingCount);
    const isFirst = currentPage <= 1;
    const isLast = currentPage >= totalPages;
    const pageSizeId = `${reactId}-page-size`;

    const goTo = React.useCallback(
      (next: number) => {
        const clamped = Math.min(Math.max(1, next), totalPages);
        if (clamped !== currentPage) onPageChange(clamped);
      },
      [currentPage, onPageChange, totalPages],
    );

    return (
      <nav
        ref={ref}
        aria-label={label}
        className={cn(
          "flex flex-wrap items-center justify-between gap-3",
          className,
        )}
        {...props}
      >
        <div aria-live="polite" className="sr-only">
          {statusText ?? `Page ${currentPage} of ${totalPages}`}
        </div>

        {onPageSizeChange && pageSize !== undefined ? (
          <div className="flex items-center gap-2">
            <label
              className="text-sm text-muted-foreground"
              htmlFor={pageSizeId}
            >
              Rows per page
            </label>
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={disabled}
              id={pageSizeId}
              onChange={(event) => {
                onPageSizeChange(Number(event.currentTarget.value));
              }}
              value={pageSize}
            >
              {pageSizeOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <span aria-hidden="true" />
        )}

        <ul className="flex items-center gap-1">
          {showEdgeButtons ? (
            <li>
              <Button
                aria-label="Go to first page"
                className={iconButtonClassName}
                disabled={disabled || isFirst}
                onClick={() => goTo(1)}
                size="sm"
                type="button"
                variant="ghost"
              >
                <ChevronsLeft aria-hidden="true" className="size-4" />
              </Button>
            </li>
          ) : null}

          <li>
            <Button
              aria-label="Go to previous page"
              className={iconButtonClassName}
              disabled={disabled || isFirst}
              onClick={() => goTo(currentPage - 1)}
              size="sm"
              type="button"
              variant="ghost"
            >
              <ChevronLeft aria-hidden="true" className="size-4" />
            </Button>
          </li>

          <li className="px-2 text-sm text-muted-foreground sm:hidden">
            Page <span className="tabular">{currentPage}</span> of{" "}
            <span className="tabular">{totalPages}</span>
          </li>

          {pages.map((entry, index) =>
            entry === "ellipsis" ? (
              <li
                aria-hidden="true"
                className="hidden size-9 select-none items-center justify-center text-sm text-muted-foreground sm:flex"
                key={`ellipsis-${index}`}
              >
                &hellip;
              </li>
            ) : (
              <li className="hidden sm:block" key={entry}>
                <Button
                  aria-current={entry === currentPage ? "page" : undefined}
                  aria-label={`Go to page ${entry}`}
                  className={cn(iconButtonClassName, "tabular")}
                  disabled={disabled}
                  onClick={() => goTo(entry)}
                  size="sm"
                  type="button"
                  variant={entry === currentPage ? "default" : "ghost"}
                >
                  {entry}
                </Button>
              </li>
            ),
          )}

          <li>
            <Button
              aria-label="Go to next page"
              className={iconButtonClassName}
              disabled={disabled || isLast}
              onClick={() => goTo(currentPage + 1)}
              size="sm"
              type="button"
              variant="ghost"
            >
              <ChevronRight aria-hidden="true" className="size-4" />
            </Button>
          </li>

          {showEdgeButtons ? (
            <li>
              <Button
                aria-label="Go to last page"
                className={iconButtonClassName}
                disabled={disabled || isLast}
                onClick={() => goTo(totalPages)}
                size="sm"
                type="button"
                variant="ghost"
              >
                <ChevronsRight aria-hidden="true" className="size-4" />
              </Button>
            </li>
          ) : null}
        </ul>
      </nav>
    );
  },
);
Pagination.displayName = "Pagination";

export { Pagination };

"use client";

import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type PaginationState,
  type RowData,
  type SortingState,
} from "@tanstack/react-table";
import {
  ChevronDown,
  ChevronUp,
  ChevronsUpDown,
  Inbox,
  Search,
  SearchX,
  X,
} from "lucide-react";
import { cn } from "@healthos/utils";
import { Button } from "./button";
import { EmptyState } from "./empty-state";
import { Input } from "./input";
import { Pagination } from "./pagination";
import { Skeleton } from "./skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./table";

declare module "@tanstack/react-table" {
  interface ColumnMeta<TData extends RowData, TValue> {
    /**
     * Marks the column as numeric: cells get `tabular` and, unless `align`
     * says otherwise, right alignment in both the header and the body.
     */
    numeric?: boolean;
    align?: "left" | "center" | "right";
    headerClassName?: string;
    cellClassName?: string;
  }
}

const alignClasses = {
  left: "text-left",
  center: "text-center",
  right: "text-right",
} as const;

type Align = keyof typeof alignClasses;

const SKELETON_WIDTHS = ["w-24", "w-32", "w-20", "w-28", "w-16"] as const;

function sortHint(sorted: false | "asc" | "desc"): string {
  if (sorted === "asc") return "Sorted ascending. Activate to sort descending.";
  if (sorted === "desc") return "Sorted descending. Activate to clear sorting.";
  return "Not sorted. Activate to sort ascending.";
}

function ariaSort(
  sorted: false | "asc" | "desc",
): "ascending" | "descending" | "none" {
  if (sorted === "asc") return "ascending";
  if (sorted === "desc") return "descending";
  return "none";
}

export interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  /**
   * Column id to filter with the search box. Omit it to hide the search box
   * entirely.
   */
  searchKey?: string;
  searchPlaceholder?: string;
  /** Title shown when there are no rows at all. */
  emptyMessage?: string;
  isLoading?: boolean;
  pageSize?: number;
  /** Visually hidden `<caption>` giving the table its accessible name. */
  caption?: string;
  /** Stable row identity; improves reconciliation across sorts and pages. */
  getRowId?: (originalRow: TData, index: number) => string;
  className?: string;
}

export function DataTable<TData, TValue>({
  columns,
  data,
  searchKey,
  searchPlaceholder = "Search…",
  emptyMessage = "No results found",
  isLoading = false,
  pageSize = 10,
  caption,
  getRowId,
  className,
}: DataTableProps<TData, TValue>) {
  const searchInputId = React.useId();
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
    [],
  );
  const [pagination, setPagination] = React.useState<PaginationState>({
    pageIndex: 0,
    pageSize,
  });

  React.useEffect(() => {
    setPagination((previous) =>
      previous.pageSize === pageSize ? previous : { pageIndex: 0, pageSize },
    );
  }, [pageSize]);

  const table = useReactTable({
    data,
    columns,
    getRowId,
    state: { sorting, columnFilters, pagination },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onPaginationChange: setPagination,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  const searchColumn = searchKey ? table.getColumn(searchKey) : undefined;
  const rawFilterValue = searchColumn?.getFilterValue();
  const searchValue = typeof rawFilterValue === "string" ? rawFilterValue : "";
  const isSearching = searchValue.length > 0;

  const leafColumnCount = Math.max(1, table.getVisibleLeafColumns().length);
  const rows = table.getRowModel().rows;
  const filteredCount = table.getFilteredRowModel().rows.length;
  const pageCount = Math.max(1, table.getPageCount());
  const currentPage = pagination.pageIndex + 1;
  const firstRowNumber =
    filteredCount === 0 ? 0 : pagination.pageIndex * pagination.pageSize + 1;
  const lastRowNumber =
    pagination.pageIndex * pagination.pageSize + rows.length;
  const skeletonRowCount = Math.max(1, Math.min(pagination.pageSize, 8));

  const statusText = isLoading
    ? "Loading results."
    : `Page ${currentPage} of ${pageCount}. Showing ${firstRowNumber} to ${lastRowNumber} of ${filteredCount} results.`;

  const clearSearch = React.useCallback(() => {
    searchColumn?.setFilterValue("");
  }, [searchColumn]);

  return (
    <div className={cn("flex w-full flex-col gap-4", className)}>
      {searchColumn ? (
        <div className="relative w-full max-w-sm">
          <label className="sr-only" htmlFor={searchInputId}>
            {searchPlaceholder}
          </label>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            className="pl-9 pr-9"
            disabled={isLoading}
            id={searchInputId}
            onChange={(event) => {
              searchColumn.setFilterValue(event.currentTarget.value);
            }}
            placeholder={searchPlaceholder}
            type="text"
            value={searchValue}
          />
          {isSearching ? (
            <button
              aria-label="Clear search"
              className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-sm p-1.5 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              onClick={clearSearch}
              type="button"
            >
              <X aria-hidden="true" className="size-4" />
            </button>
          ) : null}
        </div>
      ) : null}

      <div className="w-full overflow-x-auto rounded-lg border border-border">
        <Table aria-busy={isLoading || undefined}>
          {caption ? <caption className="sr-only">{caption}</caption> : null}
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow className="hover:bg-transparent" key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta;
                  const align: Align =
                    meta?.align ?? (meta?.numeric ? "right" : "left");
                  const canSort = header.column.getCanSort();
                  const sorted = header.column.getIsSorted();
                  const SortIcon =
                    sorted === "asc"
                      ? ChevronUp
                      : sorted === "desc"
                        ? ChevronDown
                        : ChevronsUpDown;

                  return (
                    <TableHead
                      aria-sort={canSort ? ariaSort(sorted) : undefined}
                      className={cn(alignClasses[align], meta?.headerClassName)}
                      colSpan={header.colSpan}
                      key={header.id}
                      scope="col"
                    >
                      {header.isPlaceholder ? null : canSort ? (
                        <button
                          className={cn(
                            "group inline-flex items-center gap-1.5 rounded-sm text-xs font-semibold uppercase tracking-wide transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                            align === "right" && "flex-row-reverse",
                          )}
                          disabled={isLoading}
                          onClick={header.column.getToggleSortingHandler()}
                          type="button"
                        >
                          <span>
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext(),
                            )}
                          </span>
                          <SortIcon
                            aria-hidden="true"
                            className={cn(
                              "size-3.5 shrink-0 transition-opacity",
                              sorted
                                ? "opacity-100"
                                : "opacity-40 group-hover:opacity-70",
                            )}
                          />
                          <span className="sr-only">{sortHint(sorted)}</span>
                        </button>
                      ) : (
                        flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )
                      )}
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>

          <TableBody>
            {isLoading ? (
              Array.from({ length: skeletonRowCount }, (_, rowIndex) => (
                <TableRow className="hover:bg-transparent" key={rowIndex}>
                  {table.getVisibleLeafColumns().map((column, cellIndex) => (
                    <TableCell key={column.id}>
                      <Skeleton
                        className={cn(
                          "h-4 max-w-full",
                          SKELETON_WIDTHS[
                            (rowIndex + cellIndex) % SKELETON_WIDTHS.length
                          ],
                        )}
                      />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : rows.length === 0 ? (
              <TableRow className="hover:bg-transparent">
                <TableCell className="p-0" colSpan={leafColumnCount}>
                  <EmptyState
                    action={
                      isSearching ? (
                        <Button
                          onClick={clearSearch}
                          size="sm"
                          type="button"
                          variant="outline"
                        >
                          Clear search
                        </Button>
                      ) : undefined
                    }
                    description={
                      isSearching
                        ? `Nothing matches “${searchValue}”. Try a different term.`
                        : undefined
                    }
                    icon={isSearching ? SearchX : Inbox}
                    size="sm"
                    title={emptyMessage}
                  />
                </TableCell>
              </TableRow>
            ) : (
              rows.map((row) => (
                <TableRow
                  data-state={row.getIsSelected() ? "selected" : undefined}
                  key={row.id}
                >
                  {row.getVisibleCells().map((cell) => {
                    const meta = cell.column.columnDef.meta;
                    const isNumeric =
                      meta?.numeric ?? typeof cell.getValue() === "number";
                    const align: Align =
                      meta?.align ?? (meta?.numeric ? "right" : "left");

                    return (
                      <TableCell
                        className={cn(
                          alignClasses[align],
                          isNumeric && "tabular",
                          meta?.cellClassName,
                        )}
                        key={cell.id}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext(),
                        )}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {isLoading ? (
            "Loading results…"
          ) : (
            <>
              Showing <span className="tabular">{firstRowNumber}</span>–
              <span className="tabular">{lastRowNumber}</span> of{" "}
              <span className="tabular">{filteredCount}</span>
            </>
          )}
        </p>
        <Pagination
          disabled={isLoading}
          onPageChange={(nextPage) => table.setPageIndex(nextPage - 1)}
          page={currentPage}
          pageCount={pageCount}
          statusText={statusText}
        />
      </div>
    </div>
  );
}
DataTable.displayName = "DataTable";

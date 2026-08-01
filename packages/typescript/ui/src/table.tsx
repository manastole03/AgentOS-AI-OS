import * as React from "react";
import { cn } from "@healthos/utils";

export function Table(props: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <table
      {...props}
      className={cn("w-full caption-bottom text-sm", props.className)}
    />
  );
}
export function TableHeader(
  props: React.HTMLAttributes<HTMLTableSectionElement>,
) {
  return (
    <thead {...props} className={cn("border-b bg-muted/40", props.className)} />
  );
}
export function TableBody(
  props: React.HTMLAttributes<HTMLTableSectionElement>,
) {
  return <tbody {...props} className={cn("divide-y", props.className)} />;
}
export function TableRow(props: React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      {...props}
      className={cn("transition-colors hover:bg-muted/30", props.className)}
    />
  );
}
export function TableHead(props: React.ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      {...props}
      className={cn(
        "h-11 px-4 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground",
        props.className,
      )}
    />
  );
}
export function TableCell(props: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td {...props} className={cn("px-4 py-3 align-middle", props.className)} />
  );
}

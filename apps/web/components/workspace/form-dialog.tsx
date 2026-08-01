"use client";

import { useId, type FormEvent, type ReactNode } from "react";
import { Button } from "@healthos/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@healthos/ui/dialog";
import { Label } from "@healthos/ui/label";
import { cn } from "@healthos/utils";

/**
 * The write half of a workspace: a labelled dialog wrapping one form.
 *
 * Radix owns the focus trap, the Escape key and the return of focus to the
 * trigger, so every mutation in these workspaces is reachable from the
 * keyboard without each caller re-implementing it. Submission is a real
 * `<form>` submit, so Enter works from any field.
 */

export interface FormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  submitLabel: string;
  /** Disables submit and swaps the label while the mutation is in flight. */
  isPending?: boolean;
  /**
   * Blocks submission and states why, in place of a silently disabled button.
   */
  blockedReason?: string | null;
  onSubmit: () => void;
  children: ReactNode;
  className?: string;
  /** Set for a mutation that cannot be undone. */
  destructive?: boolean;
}

export function FormDialog({
  open,
  onOpenChange,
  title,
  description,
  submitLabel,
  isPending = false,
  blockedReason,
  onSubmit,
  children,
  className,
  destructive = false,
}: FormDialogProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (isPending || blockedReason) return;
    onSubmit();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl",
          className,
        )}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? (
            <DialogDescription>{description}</DialogDescription>
          ) : null}
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-5">
          {children}
          {blockedReason ? (
            <p role="alert" className="text-sm font-medium text-destructive">
              {blockedReason}
            </p>
          ) : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="submit"
              variant={destructive ? "destructive" : "default"}
              disabled={isPending || Boolean(blockedReason)}
            >
              {isPending ? "Working…" : submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export interface FieldProps {
  label: string;
  /** Rendered under the control; also the control's accessible description. */
  hint?: ReactNode;
  required?: boolean;
  className?: string;
  /** Receives the generated id so the label and control stay associated. */
  children: (id: string) => ReactNode;
}

export function Field({
  label,
  hint,
  required = false,
  className,
  children,
}: FieldProps) {
  const id = useId();
  return (
    <div className={cn("space-y-2", className)}>
      <Label htmlFor={id}>
        {label}
        {required ? (
          <>
            <span aria-hidden="true" className="ml-0.5 text-destructive">
              *
            </span>
            <span className="sr-only"> (required)</span>
          </>
        ) : null}
      </Label>
      {children(id)}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

/** Two columns on a tablet and up, one on a phone. */
export function FieldGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2", className)}>{children}</div>
  );
}

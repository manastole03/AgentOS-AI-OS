import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Inbox, type LucideIcon } from "lucide-react";
import { cn } from "@healthos/utils";

const emptyStateVariants = cva(
  "flex flex-col items-center justify-center text-center",
  {
    variants: {
      size: {
        sm: "gap-2 px-4 py-8",
        default: "gap-3 px-6 py-12",
        lg: "gap-4 px-6 py-20",
      },
    },
    defaultVariants: { size: "default" },
  },
);

const emptyStateIconVariants = cva(
  "flex items-center justify-center rounded-full bg-muted text-muted-foreground",
  {
    variants: {
      size: {
        sm: "size-9 [&>svg]:size-4",
        default: "size-11 [&>svg]:size-5",
        lg: "size-14 [&>svg]:size-6",
      },
    },
    defaultVariants: { size: "default" },
  },
);

const emptyStateTitleVariants = cva("font-medium text-foreground", {
  variants: {
    size: {
      sm: "text-sm",
      default: "text-base",
      lg: "text-lg",
    },
  },
  defaultVariants: { size: "default" },
});

export interface EmptyStateProps
  extends
    Omit<React.HTMLAttributes<HTMLDivElement>, "title">,
    VariantProps<typeof emptyStateVariants> {
  /** Lucide icon shown above the title. Defaults to an inbox. */
  icon?: LucideIcon;
  /** Short statement of what is missing. */
  title: React.ReactNode;
  /** One sentence on why it is empty or what to do next. */
  description?: React.ReactNode;
  /** Usually a single Button; keep it to one primary path. */
  action?: React.ReactNode;
}

const EmptyState = React.forwardRef<HTMLDivElement, EmptyStateProps>(
  (
    {
      className,
      size,
      icon: Icon = Inbox,
      title,
      description,
      action,
      ...props
    },
    ref,
  ) => (
    <div
      ref={ref}
      className={cn(emptyStateVariants({ size }), className)}
      {...props}
    >
      <div aria-hidden="true" className={cn(emptyStateIconVariants({ size }))}>
        <Icon />
      </div>
      <div className="space-y-1">
        <p className={cn(emptyStateTitleVariants({ size }))}>{title}</p>
        {description ? (
          <p className="mx-auto max-w-prose text-sm text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  ),
);
EmptyState.displayName = "EmptyState";

export { EmptyState, emptyStateVariants };

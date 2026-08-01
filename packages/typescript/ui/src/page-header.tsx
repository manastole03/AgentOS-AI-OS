import * as React from "react";
import { cn } from "@healthos/utils";

export interface PageHeaderProps extends Omit<
  React.HTMLAttributes<HTMLElement>,
  "title"
> {
  /** Page title. Rendered as the heading. */
  title: React.ReactNode;
  /** Short supporting copy shown beneath the title. */
  description?: React.ReactNode;
  /** Primary/secondary actions, aligned to the end of the header. */
  actions?: React.ReactNode;
  /** Breadcrumb trail rendered above the title. */
  breadcrumb?: React.ReactNode;
  /** Heading level, so the page keeps a valid document outline. */
  headingLevel?: 1 | 2 | 3;
}

const PageHeader = React.forwardRef<HTMLElement, PageHeaderProps>(
  (
    {
      className,
      title,
      description,
      actions,
      breadcrumb,
      headingLevel = 1,
      ...props
    },
    ref,
  ) => {
    const Heading = `h${headingLevel}` as "h1" | "h2" | "h3";

    return (
      <header
        ref={ref}
        className={cn(
          "flex flex-col gap-4 border-b border-border pb-6",
          className,
        )}
        {...props}
      >
        {breadcrumb ? <div className="min-w-0">{breadcrumb}</div> : null}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
          <div className="min-w-0 space-y-1.5">
            <Heading className="text-2xl font-semibold leading-tight tracking-tight text-foreground">
              {title}
            </Heading>
            {description ? (
              <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {actions}
            </div>
          ) : null}
        </div>
      </header>
    );
  },
);
PageHeader.displayName = "PageHeader";

export { PageHeader };

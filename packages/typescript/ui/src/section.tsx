"use client";

import * as React from "react";
import { cn } from "@healthos/utils";
import { Card, CardContent, CardDescription, CardHeader } from "./card";

export interface SectionProps extends Omit<
  React.HTMLAttributes<HTMLElement>,
  "title"
> {
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Single action (button, link, menu) aligned to the end of the header. */
  action?: React.ReactNode;
  /** Heading level, so the page keeps a valid document outline. */
  headingLevel?: 2 | 3 | 4;
  /** Classes for the content wrapper inside the card. */
  contentClassName?: string;
  /** Drop the content padding, for edge-to-edge children such as tables. */
  flush?: boolean;
}

const Section = React.forwardRef<HTMLElement, SectionProps>(
  (
    {
      className,
      title,
      description,
      action,
      headingLevel = 2,
      contentClassName,
      flush = false,
      children,
      ...props
    },
    ref,
  ) => {
    const titleId = React.useId();
    const Heading = `h${headingLevel}` as "h2" | "h3" | "h4";

    return (
      <section
        ref={ref}
        aria-labelledby={titleId}
        className={cn("w-full", className)}
        {...props}
      >
        <Card>
          <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
            <div className="min-w-0 space-y-1.5">
              <Heading
                id={titleId}
                className="font-semibold leading-none tracking-tight"
              >
                {title}
              </Heading>
              {description ? (
                <CardDescription>{description}</CardDescription>
              ) : null}
            </div>
            {action ? (
              <div className="flex shrink-0 items-center gap-2">{action}</div>
            ) : null}
          </CardHeader>
          <CardContent className={cn(flush && "px-0 pb-0", contentClassName)}>
            {children}
          </CardContent>
        </Card>
      </section>
    );
  },
);
Section.displayName = "Section";

export { Section };

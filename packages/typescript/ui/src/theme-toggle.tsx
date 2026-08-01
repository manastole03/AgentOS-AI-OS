"use client";

import * as React from "react";
import { useTheme } from "next-themes";
import { Check, Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@healthos/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "./dropdown-menu";

export type ThemeToggleValue = "light" | "dark" | "system";

interface ThemeOption {
  value: ThemeToggleValue;
  label: string;
  Icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
}

const THEME_OPTIONS: readonly ThemeOption[] = [
  { value: "light", label: "Light", Icon: Sun },
  { value: "dark", label: "Dark", Icon: Moon },
  { value: "system", label: "System", Icon: Monitor },
];

const triggerClassName =
  "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-input bg-background text-foreground ring-offset-background transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50";

export interface ThemeToggleProps {
  /** Accessible name for the trigger button. */
  label?: string;
  /** Alignment of the menu relative to the trigger. */
  align?: "start" | "center" | "end";
  className?: string;
}

/**
 * Theme switcher (light / dark / system) backed by `next-themes`.
 *
 * Renders a stable, disabled placeholder with identical dimensions until the
 * component has mounted, so the server and first client render always agree.
 */
const ThemeToggle = React.forwardRef<HTMLButtonElement, ThemeToggleProps>(
  ({ label = "Toggle theme", align = "end", className }, ref) => {
    const { theme, resolvedTheme, setTheme } = useTheme();
    const [mounted, setMounted] = React.useState(false);

    React.useEffect(() => {
      setMounted(true);
    }, []);

    if (!mounted) {
      return (
        <button
          ref={ref}
          type="button"
          disabled
          className={cn(triggerClassName, className)}
        >
          <Sun className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">{label}</span>
        </button>
      );
    }

    const activeValue: ThemeToggleValue =
      theme === "light" || theme === "dark" ? theme : "system";
    const activeOption =
      THEME_OPTIONS.find((option) => option.value === activeValue) ??
      THEME_OPTIONS[2]!;
    const TriggerIcon = resolvedTheme === "dark" ? Moon : Sun;

    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          ref={ref}
          className={cn(triggerClassName, className)}
        >
          <TriggerIcon className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">
            {label} (current: {activeOption.label})
          </span>
        </DropdownMenuTrigger>
        <DropdownMenuContent align={align} className="min-w-40">
          {THEME_OPTIONS.map(({ value, label: optionLabel, Icon }) => {
            const isActive = value === activeValue;
            return (
              <DropdownMenuItem
                key={value}
                onSelect={() => setTheme(value)}
                className={cn("gap-2", isActive && "font-medium")}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="flex-1">{optionLabel}</span>
                {isActive ? (
                  <>
                    <Check className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="sr-only">(selected)</span>
                  </>
                ) : null}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  },
);
ThemeToggle.displayName = "ThemeToggle";

export { ThemeToggle };

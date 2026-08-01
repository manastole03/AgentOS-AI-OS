"use client";

import * as React from "react";
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "@healthos/utils";

export interface SliderProps
  extends React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root> {
  /**
   * Accessible label for each thumb, in thumb order. Required for range
   * sliders so screen-reader users can tell the two handles apart
   * (e.g. `["Minimum systolic", "Maximum systolic"]`).
   */
  thumbLabels?: string[];
}

const Slider = React.forwardRef<
  React.ComponentRef<typeof SliderPrimitive.Root>,
  SliderProps
>(
  (
    {
      className,
      min = 0,
      max = 100,
      value,
      defaultValue,
      thumbLabels,
      orientation = "horizontal",
      ...props
    },
    ref,
  ) => {
    const thumbValues = React.useMemo(
      () =>
        Array.isArray(value)
          ? value
          : Array.isArray(defaultValue)
            ? defaultValue
            : [min],
      [value, defaultValue, min],
    );

    return (
      <SliderPrimitive.Root
        ref={ref}
        min={min}
        max={max}
        value={value}
        defaultValue={defaultValue}
        orientation={orientation}
        className={cn(
          "relative flex touch-none select-none items-center data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
          "data-[orientation=horizontal]:h-5 data-[orientation=horizontal]:w-full",
          "data-[orientation=vertical]:h-full data-[orientation=vertical]:min-h-44 data-[orientation=vertical]:w-5 data-[orientation=vertical]:flex-col",
          className,
        )}
        {...props}
      >
        <SliderPrimitive.Track
          className={cn(
            "relative grow overflow-hidden rounded-full bg-secondary",
            "data-[orientation=horizontal]:h-2 data-[orientation=horizontal]:w-full",
            "data-[orientation=vertical]:h-full data-[orientation=vertical]:w-2",
          )}
        >
          <SliderPrimitive.Range
            className={cn(
              "absolute rounded-full bg-primary",
              "data-[orientation=horizontal]:h-full",
              "data-[orientation=vertical]:w-full",
            )}
          />
        </SliderPrimitive.Track>
        {thumbValues.map((_, index) => (
          <SliderPrimitive.Thumb
            key={index}
            aria-label={thumbLabels?.[index]}
            className={cn(
              "block h-5 w-5 rounded-full border-2 border-primary bg-background shadow-sm ring-offset-background transition-colors",
              "hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              "disabled:pointer-events-none disabled:opacity-50",
            )}
          />
        ))}
      </SliderPrimitive.Root>
    );
  },
);
Slider.displayName = SliderPrimitive.Root.displayName;

export { Slider };

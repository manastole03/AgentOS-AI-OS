"use client";

import * as React from "react";
import * as AvatarPrimitive from "@radix-ui/react-avatar";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@healthos/utils";

const avatarVariants = cva(
  "relative flex shrink-0 overflow-hidden rounded-full bg-muted",
  {
    variants: {
      size: {
        xs: "size-6 text-[0.625rem]",
        sm: "size-8 text-xs",
        default: "size-10 text-sm",
        lg: "size-12 text-base",
        xl: "size-16 text-lg",
      },
      ring: {
        none: "",
        patient:
          "ring-2 ring-role-patient ring-offset-2 ring-offset-background",
        doctor: "ring-2 ring-role-doctor ring-offset-2 ring-offset-background",
        hospital:
          "ring-2 ring-role-hospital ring-offset-2 ring-offset-background",
        insurance:
          "ring-2 ring-role-insurance ring-offset-2 ring-offset-background",
        admin: "ring-2 ring-role-admin ring-offset-2 ring-offset-background",
      },
    },
    defaultVariants: { size: "default", ring: "none" },
  },
);

export interface AvatarProps
  extends
    React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Root>,
    VariantProps<typeof avatarVariants> {}

export const Avatar = React.forwardRef<
  React.ComponentRef<typeof AvatarPrimitive.Root>,
  AvatarProps
>(({ className, size, ring, ...props }, ref) => (
  <AvatarPrimitive.Root
    ref={ref}
    className={cn(avatarVariants({ size, ring }), className)}
    {...props}
  />
));
Avatar.displayName = "Avatar";

export interface AvatarImageProps extends Omit<
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Image>,
  "alt"
> {
  /** Required. Pass the person's name, or "" when a sibling already names them. */
  alt: string;
}

export const AvatarImage = React.forwardRef<
  React.ComponentRef<typeof AvatarPrimitive.Image>,
  AvatarImageProps
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Image
    ref={ref}
    className={cn("aspect-square size-full object-cover", className)}
    {...props}
  />
));
AvatarImage.displayName = "AvatarImage";

export const AvatarFallback = React.forwardRef<
  React.ComponentRef<typeof AvatarPrimitive.Fallback>,
  React.ComponentPropsWithoutRef<typeof AvatarPrimitive.Fallback>
>(({ className, ...props }, ref) => (
  <AvatarPrimitive.Fallback
    ref={ref}
    className={cn(
      "flex size-full items-center justify-center rounded-full bg-muted font-medium uppercase text-muted-foreground",
      className,
    )}
    {...props}
  />
));
AvatarFallback.displayName = "AvatarFallback";

export { avatarVariants };

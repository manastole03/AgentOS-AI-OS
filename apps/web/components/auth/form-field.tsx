import type { ComponentProps } from "react";
import { Input } from "@healthos/ui/input";
import { Label } from "@healthos/ui/label";

export function FormField({
  label,
  id,
  ...props
}: { label: string; id: string } & ComponentProps<typeof Input>) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id} className="text-sm font-medium text-foreground">{label}</Label>
      <Input id={id} name={id} className="h-11 bg-background transition-shadow" {...props} />
    </div>
  );
}

export function FormError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
      {message}
    </p>
  );
}

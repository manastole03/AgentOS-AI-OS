"use client";

import { useRouter } from "next/navigation";
import { Button } from "@healthos/ui/button";
import { authenticatedFetch } from "@/lib/auth";

export function LogoutButton() {
  const router = useRouter();
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={async () => {
        try {
          await authenticatedFetch("/api/v1/auth/logout", { method: "POST" });
        } finally {
          router.replace("/login/patient");
          router.refresh();
        }
      }}
    >
      Sign out
    </Button>
  );
}

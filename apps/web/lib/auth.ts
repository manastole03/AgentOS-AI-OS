import type { AccountType } from "@healthos/api-types";
import { env } from "@/lib/env";

export const accountTypes: AccountType[] = [
  "patient",
  "doctor",
  "hospital",
  "insurance",
  "admin",
];

export const publicSignupTypes = accountTypes.filter(
  (type) => type !== "admin",
);

export function isAccountType(value: string): value is AccountType {
  return accountTypes.includes(value as AccountType);
}

export function accountLabel(type: AccountType): string {
  return type === "insurance"
    ? "Insurance"
    : `${type[0].toUpperCase()}${type.slice(1)}`;
}

export function getCookie(name: string): string | undefined {
  if (typeof document === "undefined") return undefined;
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

let refreshInFlight: Promise<unknown> | null = null;

function getApiUrl(path: string): string {
  return `${env.NEXT_PUBLIC_API_URL}${path}`;
}

function getApiOriginLabel(): string {
  if (env.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
  if (typeof window !== "undefined") return window.location.origin;
  return "the configured API origin";
}

function refreshSession(): Promise<unknown> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        return await apiFetch("/api/v1/auth/refresh", { method: "POST" });
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 409) throw error;
        await new Promise((resolve) => setTimeout(resolve, 300));
        return apiFetch("/api/v1/auth/refresh", { method: "POST" });
      }
    })().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  )
    headers.set("Content-Type", "application/json");
  if (init.method && !["GET", "HEAD"].includes(init.method.toUpperCase())) {
    const csrf = getCookie("healthos_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  let response: Response;
  try {
    response = await fetch(getApiUrl(path), {
      ...init,
      headers,
      credentials: "include",
    });
  } catch {
    throw new Error(
      `Unable to reach the HealthOS API at ${getApiOriginLabel()}. Verify the gateway is running and NEXT_PUBLIC_API_URL is correct.`,
    );
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: unknown;
    } | null;
    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item) =>
                typeof item === "object" && item && "msg" in item
                  ? String(item.msg)
                  : "Invalid input",
              )
              .join(". ")
          : "Request failed";
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function authenticatedFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetch<T>(path, init);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    await refreshSession();
    return apiFetch<T>(path, init);
  }
}

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const errorRate = new Rate("healthos_errors");
const portalLatency = new Trend("portal_latency", true);
const base = __ENV.BASE_URL || "http://localhost:8080";
const token = __ENV.ACCESS_TOKEN || "";

export const options = {
  scenarios: {
    public_health: {
      executor: "constant-arrival-rate",
      rate: 20,
      timeUnit: "1s",
      duration: "2m",
      preAllocatedVUs: 10,
      exec: "health",
    },
    authenticated_portal: {
      executor: "ramping-arrival-rate",
      startRate: 5,
      timeUnit: "1s",
      stages: [
        { target: 50, duration: "1m" },
        { target: 50, duration: "3m" },
        { target: 0, duration: "1m" },
      ],
      preAllocatedVUs: 50,
      maxVUs: 250,
      exec: "portal",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    healthos_errors: ["rate<0.01"],
    http_req_duration: ["p(95)<750", "p(99)<1500"],
    portal_latency: ["p(95)<1000"],
  },
};

export function health() {
  const response = http.get(`${base}/health/live`);
  errorRate.add(
    !check(response, { "gateway healthy": (value) => value.status === 200 }),
  );
  sleep(0.1);
}

export function portal() {
  if (!token)
    throw new Error("ACCESS_TOKEN is required for the authenticated scenario");
  const params = {
    headers: { Authorization: `Bearer ${token}` },
    tags: { name: "portal-overview" },
  };
  const response = http.get(`${base}/api/v1/portal/overview`, params);
  portalLatency.add(response.timings.duration);
  errorRate.add(
    !check(response, {
      "portal authorized": (value) => value.status === 200,
      "problem responses absent": (value) =>
        value.headers["Content-Type"]?.includes("application/json"),
    }),
  );
  sleep(Math.random() * 2);
}

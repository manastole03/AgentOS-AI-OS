import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json({
    service: "healthos-web",
    status: "ok",
    version: "0.1.0",
  });
}

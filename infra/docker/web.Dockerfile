FROM node:26.8.2-alpine AS base
RUN corepack enable
WORKDIR /app

FROM base AS dependencies
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/typescript/api-types/package.json packages/typescript/api-types/package.json
COPY packages/typescript/ui/package.json packages/typescript/ui/package.json
COPY packages/typescript/utils/package.json packages/typescript/utils/package.json
RUN pnpm install --frozen-lockfile

FROM base AS builder
COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=dependencies /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=dependencies /app/packages/typescript ./packages/typescript
COPY . .
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} NEXT_TELEMETRY_DISABLED=1
RUN pnpm --filter @healthos/web build

FROM node:26.8.2-alpine AS runtime
RUN addgroup --system --gid 10001 healthos && adduser --system --uid 10001 --ingroup healthos healthos
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder --chown=healthos:healthos /app/apps/web/.next/standalone ./
COPY --from=builder --chown=healthos:healthos /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=healthos:healthos /app/apps/web/public ./apps/web/public
USER healthos
EXPOSE 3000
CMD ["node", "apps/web/server.js"]

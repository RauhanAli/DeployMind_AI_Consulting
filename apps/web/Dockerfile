# DeployMind web (Next.js standalone). Build context: repository root (pnpm workspace).
FROM node:20-alpine AS deps
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN pnpm install --frozen-lockfile --filter @deploymind/web...

FROM deps AS build
COPY packages/shared packages/shared
COPY apps/web apps/web
# Next.js evaluates rewrites at build time, so the API proxy target is a build argument.
ARG API_INTERNAL_URL=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 API_INTERNAL_URL=$API_INTERNAL_URL
RUN pnpm --filter @deploymind/web build

FROM node:20-alpine AS run
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
WORKDIR /app
RUN addgroup -S web && adduser -S web -G web
COPY --from=build /repo/apps/web/.next/standalone ./
COPY --from=build /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build /repo/apps/web/public ./apps/web/public
USER web
EXPOSE 3000
CMD ["node", "apps/web/server.js"]

# Build context: repo root
FROM node:22-alpine AS builder
WORKDIR /app

# Install deps (layer-cached)
COPY services/portal/package.json services/portal/package-lock.json* ./
RUN npm ci --ignore-scripts

COPY services/portal/src ./src
COPY services/portal/svelte.config.js ./
COPY services/portal/vite.config.ts   ./
COPY services/portal/tsconfig.json    ./

RUN npm run build

FROM node:22-alpine AS runtime
LABEL org.opencontainers.image.description="ds-portal — SvelteKit data governance portal"

WORKDIR /app
RUN addgroup -S app && adduser -S -G app app

COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./
COPY --from=builder /app/package-lock.json ./
# Reuse the modules already installed in the builder (no second registry
# download), then drop dev dependencies for a lean runtime image.
COPY --from=builder /app/node_modules ./node_modules
RUN npm prune --omit=dev --ignore-scripts

USER app
EXPOSE 30004
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "require('http').get('http://localhost:30004/', r => process.exit(r.statusCode < 500 ? 0 : 1))"

ENV NODE_ENV=production PORT=30004
CMD ["node", "build"]

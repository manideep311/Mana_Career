FROM node:22-slim AS base
RUN corepack enable
WORKDIR /app

FROM base AS dev
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

FROM base AS deps
RUN corepack prepare pnpm@11 --activate
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM deps AS builder
COPY . .
# public/ may not exist in the repo yet — keep the runner COPY stable
RUN mkdir -p public
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
RUN pnpm build

FROM node:22-slim AS runner
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=3000
# The standalone server runs `node server.js` — no package manager needed at
# runtime. Drop the bundled npm/corepack/yarn: smaller image, no CVEs from
# npm's vendored deps (brace-expansion, tar, pacote, sigstore, …).
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx \
      /usr/local/lib/node_modules/corepack /usr/local/bin/corepack \
      /opt/yarn-v* /usr/local/bin/yarn /usr/local/bin/yarnpkg
RUN useradd --system --uid 10001 --create-home app
WORKDIR /app
COPY --from=builder --chown=app /app/.next/standalone ./
COPY --from=builder --chown=app /app/.next/static ./.next/static
COPY --from=builder --chown=app /app/public ./public
USER app
EXPOSE 3000
CMD ["node", "server.js"]

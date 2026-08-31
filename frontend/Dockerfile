FROM node:20-slim AS base
RUN corepack enable
WORKDIR /app

FROM base AS dev
COPY package.json pnpm-lock.yaml* ./
RUN pnpm install
COPY . .
EXPOSE 3000
CMD ["pnpm", "dev"]

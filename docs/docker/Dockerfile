#######################
# stage: base
#######################
FROM node:22-alpine AS base

RUN corepack enable && corepack prepare pnpm@11.1.1 --activate
WORKDIR /app

# Core dependency files
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

#######################
# stage: development
#######################
FROM base AS development

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy source files
COPY . .

EXPOSE 5173

# VitePress dev server with hot reload (binds 0.0.0.0 via the package script)
CMD ["pnpm", "dev"]

#######################
# stage: build
#######################
FROM base AS build

# Install dependencies
RUN pnpm install --frozen-lockfile
COPY . .
# Vendored library READMEs are surfaced as docs pages (docs/dev/lib/*.md) via
# VitePress @include. Pull them from the `libs` named build context into the
# path those includes resolve to. Supply the context when building:
#   docker build --build-context libs=../backend/lib --target build .
# (the local compose stack provides it via build.additional_contexts).
COPY --from=libs eventcore/README.md /backend/lib/eventcore/README.md
COPY --from=libs tracker/README.md   /backend/lib/tracker/README.md
COPY --from=libs uncouple/README.md  /backend/lib/uncouple/README.md
RUN pnpm run build

#######################
# stage: runtime
#######################
FROM node:22-alpine AS runtime

# Create non-root user for security
RUN addgroup -S app-user && \
    adduser -S -G app-user app-user

# Install serve globally as root, then switch user
RUN npm install -g serve

WORKDIR /app

# Copy the built static site from the build stage
COPY --from=build /app/.vitepress/dist ./dist

# Set ownership and switch to non-root user
RUN chown -R app-user:app-user /app
USER app-user

EXPOSE 5173

# Serve the built static site
CMD ["serve", "-s", "dist", "-l", "5173"]

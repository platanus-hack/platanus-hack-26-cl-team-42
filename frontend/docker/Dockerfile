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

EXPOSE 3000

# host/port come from vite.config.ts (server.host=true, server.port=3000)
CMD ["pnpm", "dev"]

#######################
# stage: build
#######################
FROM base AS build

# Install dependencies
RUN pnpm install --frozen-lockfile
COPY . .
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

# Copy built assets from build stage
COPY --from=build /app/dist ./dist

# Set ownership and switch to non-root user
RUN chown -R app-user:app-user /app
USER app-user

# Expose port
EXPOSE 3000

# Serve the static files
CMD ["serve", "-s", "dist", "-l", "3000"]

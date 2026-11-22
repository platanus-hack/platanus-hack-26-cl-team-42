# Local Docker Compose deployment
export COMPOSE_PROJECT_NAME := "multiplayer-medico"
set dotenv-load := true

# Default recipe - show available commands
default:
    @just --list


# Build services
build *args:
    docker compose -f docker-compose.yml build {{args}}

# Create your local profile (conf/local) with generated secrets. Never overwrites an existing one.
init:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -e conf/local ]; then echo "conf/local already exists; leaving it untouched."; exit 0; fi
    python3 - <<'PY'
    import secrets
    s = open("conf/local.example").read()
    s = s.replace("DJANGO_SECRET_KEY=__GENERATED__", "DJANGO_SECRET_KEY=" + secrets.token_urlsafe(50))
    open("conf/local", "w").write(s)
    PY
    chmod 600 conf/local
    echo "Created conf/local (no superuser; create one with 'just local createsuperuser' if you need it)."

# Start services
up *args:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -e "conf/${LOCAL_ENV:-local}" ] || { echo "Missing conf/${LOCAL_ENV:-local}: run 'just local init' first." >&2; exit 1; }
    # Host path of the bind-mounted backend root — eventcore docs use this so
    # Cursor/VS Code deep-links open the right files from inside Docker.
    realpath ../backend > ../backend/.eventcore-docs-host-root
    docker compose -f docker-compose.yml up -d --remove-orphans {{args}}
    echo "app:            http://{{COMPOSE_PROJECT_NAME}}.orb.local"
    echo "docs:           http://{{COMPOSE_PROJECT_NAME}}.orb.local/-docs/"
    echo "eventcore docs: http://{{COMPOSE_PROJECT_NAME}}.orb.local/-/eventcore-docs/"

# Expose the app through a temporary Cloudflare tunnel (public URL; DEBUG and the account switcher are forced off)
tunnel-up:
    #!/usr/bin/env bash
    set -euo pipefail
    [ -e "conf/${LOCAL_ENV:-local}" ] || { echo "Missing conf/${LOCAL_ENV:-local}: run 'just local init' first." >&2; exit 1; }
    docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --remove-orphans
    echo "Rotating demo passwords before the URL goes public (printed once, not stored):"
    docker compose -f docker-compose.yml -f docker-compose.tunnel.yml exec -T backend python manage.py rotate_demo_passwords
    echo "Waiting for the public URL..."
    for _ in $(seq 1 30); do
        url="$(docker compose -f docker-compose.yml -f docker-compose.tunnel.yml logs cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 || true)"
        [ -n "$url" ] && { echo "public url: $url"; exit 0; }
        sleep 2
    done
    echo "No URL yet: check 'just local tunnel-logs'." >&2; exit 1

# Show the current public tunnel URL
tunnel-url:
    @docker compose -f docker-compose.yml -f docker-compose.tunnel.yml logs cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1

# Follow the tunnel logs
tunnel-logs:
    docker compose -f docker-compose.yml -f docker-compose.tunnel.yml logs -f cloudflared

# Close the tunnel and restore the normal local settings (DEBUG, account switcher)
tunnel-down:
    docker compose -f docker-compose.yml -f docker-compose.tunnel.yml rm -sf cloudflared
    docker compose -f docker-compose.yml up -d --force-recreate backend worker

# Stop services
down *args:
    docker compose -f docker-compose.yml down {{args}}

# Run an arbitrary docker compose command against this stack
compose *args:
    @docker compose -f docker-compose.yml {{args}}

# Follow logs
logs *args:
    docker compose -f docker-compose.yml logs -f {{args}}
    
# Run Django management commands
manage +args:
    docker compose -f docker-compose.yml exec backend python manage.py {{args}}

# Open Django shell
shell:
    docker compose -f docker-compose.yml exec backend python manage.py shell

# Run migrations
migrate:
    docker compose -f docker-compose.yml exec backend python manage.py migrate

# Create superuser
createsuperuser:
    docker compose -f docker-compose.yml exec backend python manage.py createsuperuser

# Run unit tests (pytest, excluding the e2e suite that requires the running stack)
test-unit:
    docker compose -f docker-compose.yml exec -T backend \
        pytest tests/ --ignore=tests/e2e --strict-markers --strict-config -x -v

# Run end-to-end tests against the running stack (`just up` first)
test-e2e:
    docker compose -f docker-compose.yml exec -T backend \
        pytest tests/e2e --strict-markers --strict-config -x -v

# Backwards-compatible alias for unit tests
test: test-unit

# Clean up volumes and containers
clean:
    docker compose -f docker-compose.yml down -v
    docker system prune -f


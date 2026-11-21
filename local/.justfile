# Local Docker Compose deployment
export COMPOSE_PROJECT_NAME := "multiplayer-medico"
set dotenv-load := true

# Default recipe - show available commands
default:
    @just --list


# Build services
build *args:
    docker compose -f docker-compose.yml build {{args}}

# Start services
up *args:
    #!/usr/bin/env bash
    set -euo pipefail
    # Host path of the bind-mounted backend root — eventcore docs use this so
    # Cursor/VS Code deep-links open the right files from inside Docker.
    realpath ../backend > ../backend/.eventcore-docs-host-root
    docker compose -f docker-compose.yml up -d --remove-orphans {{args}}
    echo "app:            http://{{COMPOSE_PROJECT_NAME}}.orb.local"
    echo "docs:           http://{{COMPOSE_PROJECT_NAME}}.orb.local/-docs/"
    echo "eventcore docs: http://{{COMPOSE_PROJECT_NAME}}.orb.local/-/eventcore-docs/"
    echo "login:          test@localhost / test"

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


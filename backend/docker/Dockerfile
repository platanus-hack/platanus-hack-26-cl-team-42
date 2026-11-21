#######################
# stage: build-base
#######################
FROM python:3.13-slim AS build-base

ENV PYTHONDONTWRITEBYTECODE=1
# Make vendored libraries (lib/<package>/) importable by top-level name
ENV PYTHONPATH="/app/lib"
# CPU-only torch wheels (see [tool.uv.index] in pyproject.toml). `uv export` does
# not carry index URLs, so pip needs it to resolve the pinned `torch==…+cpu`.
ENV PIP_EXTRA_INDEX_URL="https://download.pytorch.org/whl/cpu"

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    # dependencies for building Python packages
    build-essential \
    # psycopg dependencies
    libpq-dev \
    # cleaning up unused files
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Install UV
RUN pip install uv

# Copy dependency files (shared layer)
COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./uv.lock

#######################
# stage: development
#######################
FROM build-base AS development

# Install additional dev dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    # Translations dependencies
    gettext \
    # Audio decoding for transcription (webm/opus, mp4/aac → PCM)
    ffmpeg \
    # Dev utils
    sudo git bash-completion nano ssh \
    # cleaning up unused files
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# dev-user
RUN groupadd --gid 1000 dev-user \
    && useradd --uid 1000 --gid dev-user --shell /bin/bash --create-home dev-user \
    && echo dev-user ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/dev-user \
    && chmod 0440 /etc/sudoers.d/dev-user

# Install dependencies (production + dev, dev group includes production)
RUN uv export --frozen --group dev --output-file requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Entrypoint
COPY ./docker/entrypoint-dev.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . .

# Set ownership and switch to dev-user
RUN chown -R dev-user:dev-user /app && \
    chown dev-user:dev-user /entrypoint.sh
USER dev-user

EXPOSE 8000

CMD [ "/entrypoint.sh" ]

#######################
# stage: build
#######################
FROM build-base AS build

# Export and build wheels for production dependencies
RUN uv export --frozen --output-file requirements.txt
RUN pip wheel --wheel-dir /usr/src/app/wheels -r requirements.txt

#######################
# stage: runtime
#######################
FROM python:3.13-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Make vendored libraries (lib/<package>/) importable by top-level name
ENV PYTHONPATH="/app/lib"
# Reject InsecureDefault fallbacks (e.g. SECRET_KEY): production config must be
# supplied explicitly via the environment. See lib/uncouple/config.py.
ENV UNCOUPLE_REQUIRE_SECURE=1

WORKDIR /app

# Install runtime only dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    # psycopg dependencies
    libpq-dev \
    # Translations dependencies
    gettext \
    # Audio decoding for transcription (webm/opus, mp4/aac → PCM)
    ffmpeg \
    # cleaning up unused files
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# Production user (non-root, no sudo)
RUN groupadd --gid 1000 app-user \
    && useradd --uid 1000 --gid app-user --shell /bin/bash --create-home app-user

# Wheel-based python dependencies
COPY --from=build /usr/src/app/wheels /wheels/
RUN pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
    && rm -rf /wheels/

# Entrypoint
COPY ./docker/entrypoint-prd.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . .

# Compile .po → .mo for every django.po found under /app.
# gettext is already installed; this is settings-free (no Django startup needed).
RUN find /app -name django.po -execdir msgfmt -o django.mo django.po \;

# Set ownership and switch to non-root user
RUN chown -R app-user:app-user /app && \
    chown app-user:app-user /entrypoint.sh
USER app-user

EXPOSE 8000

CMD [ "/entrypoint.sh" ]
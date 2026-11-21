# ruff: noqa: ERA001, E501
"""
Production-ready Django settings file.
For local development, use .default file to override necessary settings.
"""

from pathlib import Path

import dj_database_url
from django.utils.translation import gettext_lazy as _
from pydantic import field_validator

from uncouple import Config, InsecureDefault, StringList

#############################
# Directories
#############################
BASE_DIR = Path(__file__).resolve(strict=True).parent.parent
APPS_DIR = BASE_DIR / "apps"


#############################
# Configuration Classes
#############################
class DjangoConfig(Config):
    """Django general configuration"""

    DEBUG: bool = False
    SECRET_KEY: str = InsecureDefault("insecure-development-key")
    ALLOWED_HOSTS: StringList = ["*"]
    # Origins trusted for unsafe (POST/…) requests. Required for the admin over
    # HTTPS: Django checks the Origin header against this list. Supports
    # wildcard subdomains, e.g. "https://*.example.com".
    CSRF_TRUSTED_ORIGINS: StringList = []
    ADMIN_PATH: str = "admin/"
    ADMINS: str = ""
    MEDIA_URL: str = "/media/"
    TIME_ZONE: str = "UTC"
    LANGUAGE_CODE: str = "en-us"
    FRONTEND_URL: str = "http://localhost:3000"
    AUTH_USER_MODEL: str = "users.User"
    LOGIN_REDIRECT_URL: str = "/"
    LOGIN_URL: str = "/admin/login/"
    DATABASE_URL: str = "sqlite:///db.sqlite3"
    LOG_LEVEL: str = "INFO"
    SECURE_SSL_REDIRECT: bool = False
    URL_PREFIX: str = "-"
    # Host filesystem path that mirrors BASE_DIR (for eventcore docs editor links
    # when the app runs in Docker). Written automatically by `just local up`.
    EVENTCORE_DOCS_HOST_ROOT: str = ""

    @field_validator("URL_PREFIX")
    @staticmethod
    def validate_url_prefix(val: str) -> str:
        return val.strip("/")


class EmailConfig(Config):
    """Email configuration"""

    BACKEND: str = "django.core.mail.backends.console.EmailBackend"
    HOST: str = "localhost"
    PORT: int = 587
    USE_TLS: bool = True
    HOST_USER: str = ""
    HOST_PASSWORD: str = ""
    SUBJECT_PREFIX: str = ""
    DEFAULT_FROM: str = "root@localhost"
    SERVER: str = "root@localhost"


class CeleryConfig(Config):
    """Celery configuration"""

    BROKER_URL: str = "redis://redis:6379/0"
    RESULT_BACKEND: str = "redis://redis:6379/0"


class ProjectConfig(Config):
    """Project-specific configuration"""

    ...


# Load configurations
django_config = DjangoConfig.load(prefix="DJANGO")
email_config = EmailConfig.load(prefix="EMAIL")
celery_config = CeleryConfig.load(prefix="CELERY")
project_config = ProjectConfig.load(prefix="PROJECT")

#############################
# GENERAL
#############################
DEBUG = django_config.DEBUG
SECRET_KEY = django_config.SECRET_KEY
ALLOWED_HOSTS = django_config.ALLOWED_HOSTS

TIME_ZONE = django_config.TIME_ZONE
SITE_ID = 1
USE_TZ = True

#############################
# INTERNATIONALIZATION (i18n) & LOCALIZATION (l10n)
#############################
# Strings are marked for translation the standard Django way with
# gettext / gettext_lazy. Translations are stored in committed ``django.po``
# files (standard domain) and compiled to ``django.mo`` at image build / dev
# startup. The ``dbi18n`` app (lib/dbi18n) adds a live DB overlay: Translation
# rows win at runtime and let translators edit strings without a redeploy.
# The typical workflow is: mark strings → makemessages → edit in admin (live)
# → i18n_export (download tarball) → i18n_import (merge into .po) → commit
# → deploy → prune. See lib/dbi18n/README.md.
# https://docs.djangoproject.com/en/stable/topics/i18n/
USE_I18N = True

# Default language used when the request does not select another. The active
# language is resolved per-request by ``LocaleMiddleware`` (Accept-Language
# header, session, or cookie).
LANGUAGE_CODE = django_config.LANGUAGE_CODE

# Languages offered by this project. ``LocaleMiddleware`` will only switch to a
# language listed here. To add a language: add it here, run
# ``just backend messages <lang>``, translate the .po, and run
# ``just backend compilemessages``.
LANGUAGES = [
    ("en", _("English")),
    ("es", _("Spanish")),
]

# The first LOCALE_PATHS entry is the consolidated project catalog and the
# target that ``i18n_import`` writes to.  Django gives it the highest
# file-catalog priority (overrides app-level locale/ dirs and bundled packages).
LOCALE_PATHS = [BASE_DIR / "locale"]

# Max seconds before a worker rebuilds its in-memory catalog to pick up
# translation edits made in another process (see lib/dbi18n).
DBI18N_RELOAD_SECONDS = 30

USE_X_FORWARDED_HOST = True
URL_PREFIX = django_config.URL_PREFIX
EVENTCORE_DOCS_HOST_ROOT = django_config.EVENTCORE_DOCS_HOST_ROOT


#############################
# DATABASES
#############################
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
DATABASES = {"default": dj_database_url.parse(django_config.DATABASE_URL)}

# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


##############################
# STORAGES
#############################
STORAGES = {
    # Archivos subidos (p. ej. audios de dictados). No se exponen vía MEDIA_URL:
    # cada módulo los sirve a través de su API autenticada.
    # TODO: usar S3 (deploy/terraform/webapp/storage) en entornos desplegados.
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

#############################
# URLS
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF = "conf.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "wsgi.application"


#############################
# ADMIN
#############################
ADMIN_PATH = django_config.ADMIN_PATH
ADMINS = (
    [tuple(s.strip().split(":")) for s in django_config.ADMINS.split(",") if ":" in s]
    if django_config.ADMINS
    else []
)
MANAGERS = ADMINS


#############################
# APPS
#############################
INSTALLED_APPS = [
    ############################
    # Common Django apps
    ############################
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.forms",
    ############################
    # Third-party apps
    ############################
    "rest_framework",
    "drf_spectacular",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.amazon_cognito",
    "allauth.headless",
    "allauth.usersessions",
    "corsheaders",
    "django_extensions",
    ############################
    # Local/Custom apps
    ############################
    "eventcore.app",
    "apps.transcription",
    "eventcore.contrib.docs",
    "dbi18n",
    "apps.users",
    "apps.demo",
    "apps.recordings",
]


#############################
# AUTHENTICATION
#############################
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_USER_MODEL = django_config.AUTH_USER_MODEL
LOGIN_REDIRECT_URL = django_config.LOGIN_REDIRECT_URL
LOGIN_URL = django_config.LOGIN_URL


#############################
# PASSWORDS
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


#############################
# MIDDLEWARE
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    # Keeps each process's DB-backed translation catalog fresh (see dbi18n).
    # Must come after LocaleMiddleware so the active language is already set.
    "dbi18n.middleware.DbTranslationMiddleware",
    "django.middleware.common.CommonMiddleware",
    # CSRF disabled for auth endpoints
    # "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]


#############################
# STATIC
#############################
STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = f"/{URL_PREFIX}/static/" if URL_PREFIX else "/static/"
STATICFILES_DIRS = [str(APPS_DIR / "static")] if (APPS_DIR / "static").exists() else []
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]


#############################
# MEDIA
#############################
MEDIA_ROOT = str(APPS_DIR / "media")
MEDIA_URL = django_config.MEDIA_URL


#############################
# TEMPLATES
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")] if (APPS_DIR / "templates").exists() else [],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"


#############################
# FIXTURES
#############################
FIXTURE_DIRS = (str(APPS_DIR / "fixtures"),) if (APPS_DIR / "fixtures").exists() else ()


#############################
# SECURITY
#############################
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False
X_FRAME_OPTIONS = "DENY"
SECURE_SSL_REDIRECT = django_config.SECURE_SSL_REDIRECT
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# The Django admin enforces CSRF (even though the global CsrfViewMiddleware is
# disabled for the API), so admin POSTs over HTTPS need the serving origin
# listed here. Set DJANGO_CSRF_TRUSTED_ORIGINS in each environment (the local
# stack defaults it to the OrbStack domain).
CSRF_TRUSTED_ORIGINS = django_config.CSRF_TRUSTED_ORIGINS


# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# WARNING - CSRF disabled
# !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
# CSRF_COOKIE_HTTPONLY = False
# CSRF_COOKIE_SECURE = bool(security_config.SECURE_SSL_REDIRECT)
# CSRF_COOKIE_NAME = "__Secure-csrftoken" if CSRF_COOKIE_SECURE else "csrftoken"


#############################
# EMAIL
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
# If EMAIL_BACKEND is empty, use console backend (local development)
EMAIL_BACKEND = email_config.BACKEND

# Production email settings (only set when EMAIL_BACKEND is configured for SMTP)
EMAIL_HOST = email_config.HOST
EMAIL_PORT = email_config.PORT
EMAIL_USE_TLS = email_config.USE_TLS
EMAIL_HOST_USER = email_config.HOST_USER
EMAIL_HOST_PASSWORD = email_config.HOST_PASSWORD
DEFAULT_FROM_EMAIL = email_config.DEFAULT_FROM
SERVER_EMAIL = email_config.SERVER
EMAIL_SUBJECT_PREFIX = email_config.SUBJECT_PREFIX
EMAIL_TIMEOUT = 5


#############################
# CACHING
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    },
}


#############################
# LOGGING
#############################
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
LOG_LEVEL = django_config.LOG_LEVEL
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": LOG_LEVEL,
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": LOG_LEVEL, "handlers": ["console"]},
    "loggers": {
        "django.db.backends": {
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
        "django.security.DisallowedHost": {
            "level": "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
        # Silence noisy inotify file-watch events from the autoreloader
        "watchdog": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
        },
    },
}

#############################
# CORS
#############################
# https://github.com/adamchainz/django-cors-headers
CORS_ALLOWED_ORIGINS = [django_config.FRONTEND_URL]
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["X-Session-Token"]

# Allow cookies to be sent cross-origin
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = False  # not DEBUG  # Require HTTPS in production


#############################
# django-allauth
#############################
# Headless API Configuration
# https://docs.allauth.org/en/latest/headless/index.html
HEADLESS_ONLY = False

# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ALLOW_REGISTRATION = True
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
ACCOUNT_EMAIL_VERIFICATION = "none"

SOCIALACCOUNT_ONLY = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True


#############################
# PROJECT SPECIFIC SETTINGS
#############################
# MY_SETTING = project_config.MY_SETTING


#############################
# DJANGO REST FRAMEWORK
#############################
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "eventcore.contrib.drf.CsrfExemptSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Multiplayer Médico API",
    "DESCRIPTION": "Multiplayer Médico API.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

#############################
# CELERY
#############################
# https://docs.celeryq.dev/en/stable/userguide/configuration.html
CELERY_BROKER_URL = celery_config.BROKER_URL
CELERY_RESULT_BACKEND = celery_config.RESULT_BACKEND
CELERY_RESULT_EXTENDED = True
CELERY_TASK_TRACK_STARTED = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"

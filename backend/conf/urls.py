# ruff: noqa: I001
# Import order here is intentional: eventcore.contrib.drf must come before
# anything that imports rest_framework.views (including drf_spectacular.views).
# See the docstring in eventcore/contrib/drf.py for why.
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django.views import defaults as default_views
from ninja import NinjaAPI
from ninja.security import SessionAuth

from eventcore.contrib.drf import command_urlpatterns
from eventcore.contrib.docs import router as eventcore_docs_router

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Celery only imports task modules in the worker; import them here too so the
# web process can list/dispatch them through the tracker API.
import apps.demo.tasks  # noqa: F401
from apps.clinical_templates.api import router as clinical_templates_router
from apps.demo.api import router as demo_router
from apps.agent.api import router as agent_router
from apps.recordings.api import router as recordings_router
from apps.recordings.patients_api import router as patients_router
from apps.transcription.api import router as transcription_router
from apps.transcription.episode_api import router as episodes_router
from apps.users.dev_api import router as dev_router
from tracker.api import router as tracker_router

########################
# API Configuration
########################
API_ROUTERS = [
    ("/demo", demo_router),
    ("/recordings", recordings_router),
    ("/patients", patients_router),
    ("/episodes", episodes_router),
    ("/dev", dev_router),
    ("/clinical-templates", clinical_templates_router),
    ("/tracker", tracker_router),
    ("/transcription", transcription_router),
    ("/agent", agent_router),
    ("/eventcore", eventcore_docs_router),
]

# Configuration process guards against multiple
session_auth = sync_to_async(SessionAuth(csrf=False))
api = NinjaAPI(title="API", version="1.0.0", auth=session_auth)
for route_path, router in API_ROUTERS:
    if not getattr(router, "api", None):
        api.add_router(route_path, router)


########################
# Django URL Configuration
########################
_base_urlpatterns = [
    ######################
    # Base URLs
    ######################
    path(settings.ADMIN_PATH, admin.site.urls),
    path("users/", include("apps.users.urls", namespace="users")),
    path(".auth/accounts/", include("allauth.urls")),
    path(".auth/headless/", include("allauth.headless.urls")),
    path("api/", lambda request: JsonResponse({"title": api.title, "version": api.version})),
    path("api/", api.urls),
    path("api/commands/", include((command_urlpatterns(), "commands"))),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/schema/swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("_health/", lambda request: JsonResponse({"status": "ok"})),
    path("eventcore-docs/", include("eventcore.contrib.docs.urls")),
    ######################
    # Additional URLs
    ######################
    # path(include("apps.myapp.urls", namespace="myapp")),
]


if settings.DEBUG:
    _base_urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]

urlpatterns = [path(f"{settings.URL_PREFIX}/", include(_base_urlpatterns))]

# Make the Celery app available as ``conf.celery_app`` so workers and
# beat schedulers can be started with ``-A conf``.
from .celery import app as celery_app  # noqa: F401

__all__ = ["celery_app"]

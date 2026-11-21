from django.core.management.base import BaseCommand

from apps.clinical_templates.services import sync_templates_from_files


class Command(BaseCommand):
    help = "Sync ICU clinical templates from apps/clinical_templates/data into the database."

    def handle(self, *args, **options):
        for result in sync_templates_from_files():
            status = "created" if result.created else "unchanged"
            self.stdout.write(f"{result.slug} v{result.version}: {status}")

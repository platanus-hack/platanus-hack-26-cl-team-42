"""Sync the SourceString universe from committed ``django.po`` files."""

from django.core.management.base import BaseCommand

from dbi18n.pofiles import sync_source_strings


class Command(BaseCommand):
    help = (
        "Parse all committed django.po files and upsert the SourceString universe. "
        "Marks strings absent from every .po file as stale."
    )

    def handle(self, **options):
        sync_source_strings(stdout=self.stdout)

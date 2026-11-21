"""Database-backed gettext translations, editable from the Django admin.

Keep marking strings with ``gettext`` / ``gettext_lazy`` as usual; this app
serves the translations from the ``Translation`` model instead of ``.po`` /
``.mo`` files. See ``README.md`` for the full picture.
"""

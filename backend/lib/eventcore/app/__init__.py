"""Optional Django app that persists an eventcore audit trail.

Installing ``eventcore.app`` (add it to ``INSTALLED_APPS``) records a
:class:`~eventcore.app.models.LogRecord` row for every command invocation
(via an ``on(Command, ...)`` subscriber) and every applied event (via an
``on(Event, ...)`` subscriber). The core ``eventcore`` library never imports
this app, so it is entirely opt-in.
"""

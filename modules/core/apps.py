from pathlib import Path

from django.apps import AppConfig
from django.conf import settings
from django.utils.autoreload import autoreload_started


def _watch_env(sender, **kwargs):
    # settings.py reads .env at startup; restart runserver when it changes.
    sender.watch_dir(Path(settings.BASE_DIR), ".env")


class CoreConfig(AppConfig):
    name = "modules.core"

    def ready(self):
        autoreload_started.connect(_watch_env)

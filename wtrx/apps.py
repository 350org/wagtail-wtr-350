from django.apps import AppConfig


class WtrxConfig(AppConfig):
    name = "wtrx"
    label = "wtrx"
    verbose_name = "With the Ranks Extensions"

    def ready(self):
        from wtrx.signals import connect_signals

        connect_signals()

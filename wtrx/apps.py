from django.apps import AppConfig


class WtrxConfig(AppConfig):
    name = "wtrx"
    label = "wtrx"
    verbose_name = "With the Ranks Extensions"

    def ready(self):
        pass

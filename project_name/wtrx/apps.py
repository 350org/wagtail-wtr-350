from django.apps import AppConfig


class WtrxConfig(AppConfig):
    name = "{{ project_name }}.wtrx"
    label = "{{ project_name }}_wtrx"
    verbose_name = "With the Ranks Extensions"

    def ready(self):
        pass

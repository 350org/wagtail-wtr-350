from django.apps import AppConfig


class HomeConfig(AppConfig):
    name = "{{ project_name }}.home"
    label = "{{ project_name }}_home"
    verbose_name = "Home"

from django.apps import AppConfig


class SearchConfig(AppConfig):
    name = "{{ project_name }}.search"
    label = "{{ project_name }}_search"
    verbose_name = "Search"

from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "{{ project_name }}.users"
    label = "{{ project_name }}_users"
    verbose_name = "Users"

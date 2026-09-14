from django.apps import AppConfig


class WtrxConfig(AppConfig):
    name = "wtrx"
    label = "wtrx"
    verbose_name = "With the Ranks Extensions"

    def ready(self):
        from wtrx.ai import patch_content_feedback_prompt_default
        from wtrx.forms import patch_wagtail_2fa_device_form
        from wtrx.signals import connect_signals

        connect_signals()
        patch_wagtail_2fa_device_form()
        patch_content_feedback_prompt_default()

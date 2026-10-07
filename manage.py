#!/usr/bin/env python
import os
import sys

from dotenv import load_dotenv


def main():
    # No-ops if .env doesn't exist (e.g. production, where the platform sets
    # env vars directly) and never overrides vars already set in the shell.
    load_dotenv()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wagtail_wtr.settings.dev")

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()

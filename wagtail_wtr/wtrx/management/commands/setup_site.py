"""
Interactive site setup command.

Run via ``make setup`` or ``python manage.py setup_site``.

Creates an initial Site object, HomePage instance (placed at the Wagtail page
tree root), and IntegrationSettings record. Optionally prompts for language
and platform configuration.
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from wagtail.models import Page, Site


DONATION_PLATFORM_CHOICES = [
    ("none", "None"),
    ("actblue", "ActBlue"),
]

SIGNUP_PLATFORM_CHOICES = [
    ("wagtail_forms", "Wagtail Forms (built-in)"),
    ("action_network", "Action Network"),
    ("none", "None"),
]


class Command(BaseCommand):
    help = "Interactive initial site setup — creates Site, HomePage, and IntegrationSettings."

    def handle(self, *args, **options):
        # Deferred imports to avoid import-time DB access (architecture rule #4).
        from wagtail_wtr.home.models import HomePage
        from wagtail_wtr.wtrx.site_settings import IntegrationSettings

        self.stdout.write(self.style.MIGRATE_HEADING("wagtail-wtr site setup"))
        self.stdout.write("")

        # ------------------------------------------------------------------
        # 1. Site name
        # ------------------------------------------------------------------
        site_name = self._prompt("Site name", default="My Site")

        # ------------------------------------------------------------------
        # 2. Language
        # ------------------------------------------------------------------
        language_choices = [(code, label) for code, label in settings.LANGUAGES]
        default_lang = settings.LANGUAGE_CODE or "en"
        language = self._prompt_choice(
            "Site language",
            choices=language_choices,
            default=default_lang,
        )

        # ------------------------------------------------------------------
        # 3. Donation platform
        # ------------------------------------------------------------------
        donation_platform = self._prompt_choice(
            "Donation platform",
            choices=DONATION_PLATFORM_CHOICES,
            default="none",
        )

        donation_base_url = ""
        donation_suggested_amounts = ""
        if donation_platform != "none":
            donation_base_url = self._prompt(
                "Donation base URL (e.g. https://secure.actblue.com/donate/mycampaign)",
                default="",
            )
            donation_suggested_amounts = self._prompt(
                "Suggested donation amounts (comma-separated integers)",
                default="10,25,50,100",
            )
            # Validate the amounts
            self._validate_amounts(donation_suggested_amounts)

        # ------------------------------------------------------------------
        # 4. Signup platform
        # ------------------------------------------------------------------
        signup_platform = self._prompt_choice(
            "Signup platform",
            choices=SIGNUP_PLATFORM_CHOICES,
            default="wagtail_forms",
        )

        # ------------------------------------------------------------------
        # 5. Create objects
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Creating site objects..."))

        # Get or verify the Wagtail root page
        root_page = Page.objects.filter(depth=1).first()
        if root_page is None:
            self.stderr.write(
                self.style.ERROR(
                    "No root page found. Run 'python manage.py migrate' first."
                )
            )
            return

        # Check if a HomePage already exists
        existing_home = HomePage.objects.first()
        if existing_home:
            self.stdout.write(
                f'  HomePage already exists: "{existing_home.title}" (pk={existing_home.pk})'
            )
            home = existing_home
        else:
            # Remove the Wagtail default placeholder page (if present) to
            # free the "home" slug for our real HomePage.
            placeholder = (
                Page.objects.filter(depth=2, slug="home")
                .exclude(pk__in=HomePage.objects.values_list("pk", flat=True))
                .first()
            )
            if placeholder:
                placeholder.delete()
                self.stdout.write("  Removed Wagtail default placeholder page")
                # Refresh root_page from the DB so treebeard's internal
                # state is consistent after the child deletion.
                root_page.refresh_from_db()

            home = HomePage(
                title=site_name,
                slug="home",
            )
            root_page.add_child(instance=home)
            self.stdout.write(
                self.style.SUCCESS(f'  Created HomePage: "{home.title}" (pk={home.pk})')
            )

        # Create or update Site
        site, created = Site.objects.get_or_create(
            is_default_site=True,
            defaults={
                "hostname": "localhost",
                "port": 80,
                "site_name": site_name,
                "root_page": home,
            },
        )
        if not created:
            site.site_name = site_name
            site.root_page = home
            site.save()
            self.stdout.write(f'  Updated default Site: "{site_name}"')
        else:
            self.stdout.write(
                self.style.SUCCESS(f'  Created default Site: "{site_name}"')
            )

        # Create or update IntegrationSettings
        integration, _created = IntegrationSettings.objects.get_or_create(
            site=site,
        )
        integration.donation_platform = donation_platform
        integration.donation_base_url = donation_base_url
        integration.donation_suggested_amounts = donation_suggested_amounts
        integration.signup_platform = signup_platform
        integration.save()
        self.stdout.write(self.style.SUCCESS("  Configured IntegrationSettings"))

        # Update LANGUAGE_CODE note
        if language != default_lang:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"  Note: To change the site language to '{language}', update "
                    f"LANGUAGE_CODE in your settings file."
                )
            )

        # ------------------------------------------------------------------
        # Done
        # ------------------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Setup complete!"))
        self.stdout.write(
            "  Run 'make dev' to start the development server, then visit "
            "http://localhost:8000/admin/ to log in."
        )
        self.stdout.write(
            "  If you haven't created a superuser yet, run 'make createsuperuser'."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _prompt(self, label, default=""):
        """
        Prompt the user for free-text input with an optional default.

        Returns the user's input or the default if input is empty.
        """
        if default:
            prompt_str = f"{label} [{default}]: "
        else:
            prompt_str = f"{label}: "

        value = input(prompt_str).strip()
        if not value:
            value = default
        return value

    def _prompt_choice(self, label, choices, default=""):
        """
        Prompt the user to pick from a numbered list of choices.

        ``choices`` is a list of (value, display_label) tuples.
        ``default`` is the value (not the number) to use when the user
        presses Enter without typing anything.

        Returns the selected value string.
        """
        self.stdout.write(f"  {label}:")
        default_num = None
        for i, (value, display) in enumerate(choices, 1):
            marker = " (default)" if value == default else ""
            self.stdout.write(f"    {i}. {display}{marker}")
            if value == default:
                default_num = i

        prompt_str = f"  Enter choice [{default_num or 1}]: "

        while True:
            raw = input(prompt_str).strip()
            if not raw:
                return default

            try:
                num = int(raw)
            except ValueError:
                self.stderr.write(
                    self.style.ERROR(f"  Enter a number between 1 and {len(choices)}.")
                )
                continue

            if 1 <= num <= len(choices):
                return choices[num - 1][0]

            self.stderr.write(
                self.style.ERROR(f"  Enter a number between 1 and {len(choices)}.")
            )

    def _validate_amounts(self, amounts_str):
        """Validate comma-separated integer string. Warn but don't abort."""
        if not amounts_str:
            return
        try:
            [int(x.strip()) for x in amounts_str.split(",") if x.strip()]
        except ValueError:
            self.stderr.write(
                self.style.WARNING(
                    "  Warning: amounts should be comma-separated integers (e.g. 10,25,50,100). "
                    "Saving as-is; validation will apply when editing in admin."
                )
            )

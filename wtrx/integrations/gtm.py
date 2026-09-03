"""
Google Tag Manager / Google Analytics integration — paste Google's own
setup snippets verbatim, no server-side API calls.

Same "paste it exactly as given" pattern as FundraiseUpConfigBlock's
installation_code (fundraiseup.py): rather than collecting a container/
measurement ID here and hand-generating the exact script markup (which
would need maintaining against whatever format Google's own snippet
happens to be this year), the editor pastes Google's own setup-flow
snippet(s) directly, and IntegrationSettings.head_html()/body_html()
(site_settings.py) render them verbatim.

head_snippet is typically Tag Manager's own <script> tag (from Tag
Manager's "Install Google Tag Manager" step 1, tagmanager.google.com). If
the site uses Tag Manager to manage Analytics — Google's own recommended
setup — that's all that's needed here; Analytics itself gets configured
inside the Tag Manager container, not in this repo. A site that wants
Analytics directly without Tag Manager can instead paste the standalone
gtag.js snippet (googletagmanager.com/gtag/js) here — both are just
<script> tags meant for <head>, so either works, and both can be pasted
together if genuinely needed.

body_snippet is Tag Manager's <noscript> fallback iframe (step 2 of the
same setup flow) — optional, since an Analytics-only site (no Tag
Manager) has no equivalent body snippet to paste.
"""

from django.utils.translation import gettext_lazy as _
from wagtail.blocks import BooleanBlock, StructBlock, TextBlock

from wtrx.integrations.registry import IntegrationType, register_integration


class GoogleTagManagerConfigBlock(StructBlock):
    """Per-site Google Tag Manager / Analytics configuration, added as an entry in Settings > Integrations."""

    enabled = BooleanBlock(
        required=False,
        default=True,
        label=_("Enabled"),
        help_text=_(
            "Uncheck to temporarily disable Tag Manager/Analytics without "
            "removing its configuration."
        ),
    )
    head_snippet = TextBlock(
        label=_("Head snippet"),
        help_text=_(
            "The script snippet from Google Tag Manager's or Google "
            "Analytics' own setup instructions, pasted exactly as given. "
            "Rendered once near the top of the site's page head while this "
            "integration is enabled."
        ),
    )
    body_snippet = TextBlock(
        required=False,
        label=_("Body snippet"),
        help_text=_(
            "Optional. Google Tag Manager's noscript fallback snippet, "
            "if you're using Tag Manager — a standalone Analytics-only "
            "setup has no equivalent snippet to paste here. Rendered "
            "immediately after the page body opens while this integration "
            "is enabled."
        ),
    )

    class Meta:
        icon = "code"
        label = _("Google Tag Manager / Analytics")


register_integration(
    IntegrationType(
        slug="google_tag_manager",
        label=_("Google Tag Manager / Analytics"),
        category="analytics",
        head_html_field="head_snippet",
        body_html_field="body_snippet",
    )
)

import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder
from django.utils.html import _json_script_escapes, format_html
from django.utils.safestring import mark_safe
from wagtail.models import Site

from wtrx.blocks import background_is_light as _background_is_light, resolve_background
from wtrx.integrations import actionkit
from wtrx.site_settings import (
    SOCIAL_PLATFORM_CHOICES,
    BrandingSEOSettings,
    FooterSettings,
    IntegrationSettings,
    NavigationSettings,
    SocialSettings,
)


register = template.Library()

# Wagtail site settings are available in all templates via the context processor
# registered in settings/base.py:
#   "wagtail.contrib.settings.context_processors.settings"
#
# Access in templates using the dot-notation path to the settings model:
#   settings.wtrx.BrandingSEOSettings.site_description
#
# where <app_label> is "wtrx" (the app label set in wtrx/apps.py).
#
# Alternatively, use the Wagtail built-in tag for one-off access:
#   load wagtailsettings_tags
#   get_settings
#   settings.wtrx.BrandingSEOSettings.site_description
#
# Add project-specific template tags below.


# ---------------------------------------------------------------------------
# Background palette helpers
# ---------------------------------------------------------------------------


@register.filter
def background_key(value):
    """
    Normalise a stored background value to its canonical palette key.

    Every block with a background choice draws its fill from one shared
    palette (BACKGROUND_COLOR_CHOICES) and renders it as a
    `.wtr-bg-{key}` class. Content saved before the palette was unified —
    and any page revision reverted to from before it — can still hold a
    per-block legacy key ("light", "dark", "muted", ...), so the class name
    is always built through this filter rather than interpolating the raw
    value:

        <div class="wtr-bg-{{ value.background|background_key }}">
    """
    return resolve_background(value)


@register.filter
def background_is_light(value):
    """
    True when a background needs dark text, a dark-outline button and an
    inverted eyebrow pill instead of the light-on-color default.

    Templates branch on this rather than testing colour keys inline, so
    adding a light fill to the palette does not mean hunting down a
    scattered `== 'light-grey'` check across five block templates:

        {% if value.background|background_is_light %}text-dark{% else %}text-light{% endif %}
    """
    return _background_is_light(value)


# ---------------------------------------------------------------------------
# Navigation helpers
# ---------------------------------------------------------------------------


def _resolved_attr(resolved, name, default=""):
    """
    Read ``name`` off whatever NavigationSettings/FooterSettings.resolved_for_page()
    returned — either the settings model instance itself (a real object, plain
    ``getattr`` works) or a StructValue from an override entry (a bare
    ``collections.OrderedDict`` with no attribute access at all). Django
    templates paper over this by trying dict-lookup before ``getattr`` on
    every ``{{ var.attr }}``, but that resolution only happens inside the
    template engine — plain Python code (like a simple_tag's function body)
    needs this explicitly, or a StructValue field silently reads back as the
    default every time.
    """
    if isinstance(resolved, dict):
        return resolved.get(name, default)
    return getattr(resolved, name, default)


@register.simple_tag(takes_context=True)
def resolved_navigation(context):
    """
    Return the NavigationSettings-shaped object to render for the current
    page: the site's default NavigationSettings, or the most specific
    matching entry from its navigation_overrides if the current page falls
    under one of their root pages. See
    NavigationSettings.resolved_for_page().

    Usage in templates:
        {% load wtrx_tags %}
        {% resolved_navigation as nav %}
    """
    request = context.get("request")
    if request is None:
        return None
    nav_settings = NavigationSettings.for_request(request)
    return nav_settings.resolved_for_page(context.get("page"))


@register.simple_tag(takes_context=True)
def resolved_footer(context):
    """
    Return the FooterSettings-shaped object to render for the current page:
    the site's default FooterSettings, or the most specific matching entry
    from its footer_overrides if the current page falls under one of their
    root pages. See FooterSettings.resolved_for_page().

    Usage in templates:
        {% load wtrx_tags %}
        {% resolved_footer as footer %}
    """
    request = context.get("request")
    if request is None:
        return None
    footer_settings = FooterSettings.for_request(request)
    return footer_settings.resolved_for_page(context.get("page"))


@register.simple_tag(takes_context=True)
def resolved_footer_newsletter_signup(context):
    """
    Fetch (and cache) the ActionKit form powering the footer's newsletter
    signup box, for whichever footer is resolved for the current page — the
    resolved footer's own newsletter_actionkit_shortname (site default or
    footer override), the same auto-rendered-form mechanism
    SignupActionKitBlock uses for its own panel (see
    actionkit.fetch_and_cache_embed_form_html).

    Returns a dict with `form_html`, `actionkit_base_url`, and
    `success_message` — suitable for including directly into
    wtrx/components/streamfield/blocks/_actionkit_form.html — or None when
    no shortname is configured for this page's footer, meaning no signup box
    should render at all.

    Unlike every other field on FooterOverrideBlock, `newsletter_success_message`
    falls back to the site FooterSettings' own value when an override leaves
    it blank, rather than resolving to nothing: _actionkit_form.html's inline
    AJAX submit path (see its wireInlineSubmit()) only wires up when a success
    message is present, and the footer box is scoped per-instance (see that
    template) specifically so it works no matter where it sits relative to
    other ActionKit embeds on the page — an override that forgets to set its
    own message shouldn't silently regress to relying on ActionKit's own
    script, which only ever binds the first embed in the DOM.

    Usage in templates (after {% resolved_footer as footer %}):
        {% load wtrx_tags %}
        {% resolved_footer_newsletter_signup as newsletter %}
    """
    request = context.get("request")
    footer = context.get("footer")
    if request is None or footer is None:
        return None
    short_form_id = _resolved_attr(footer, "newsletter_actionkit_shortname", "")
    if not short_form_id:
        return None

    hostname = ""
    try:
        config = IntegrationSettings.for_request(request).get_integration_config("actionkit")
        hostname = config.get("hostname", "") if config else ""
    except (IntegrationSettings.DoesNotExist, Site.DoesNotExist):
        hostname = ""

    form_html = None
    if hostname:
        form_html = actionkit.fetch_and_cache_embed_form_html(hostname, short_form_id)

    success_message = _resolved_attr(footer, "newsletter_success_message", "")
    if not success_message:
        try:
            success_message = FooterSettings.for_request(request).newsletter_success_message
        except (FooterSettings.DoesNotExist, Site.DoesNotExist):
            success_message = ""

    return {
        "form_html": form_html,
        "actionkit_base_url": actionkit.base_url(hostname) if hostname else "",
        "success_message": success_message,
    }


def _page_is_within(page, target):
    """
    True when ``page`` is ``target`` itself or a descendant of it. Wagtail
    stores tree paths as fixed-width segments, so a string prefix test is an
    exact ancestry test (the same trick NavigationSettings.resolved_for_page()
    uses to match override root pages).
    """
    if target is None:
        return False
    return page.path.startswith(target.path)


@register.simple_tag(takes_context=True)
def nav_item_is_active(context, item):
    """
    True when a primary-navigation item points at the section the visitor is
    currently in — used to draw the active underline in header.html.

    An internal link matches its own page and everything beneath it; a submenu
    matches when any of its internal children does, so "Media & Resources"
    stays underlined while you are reading a blog post under it. External and
    anchor links never match: there is no reliable way to tell whether an
    arbitrary URL or on-page anchor is "the current page".

    Usage in templates:
        {% load wtrx_tags %}
        {% nav_item_is_active item as is_active %}
    """
    page = context.get("page")
    if page is None:
        return False
    if item.block_type == "internal":
        return _page_is_within(page, item.value.get("page"))
    if item.block_type == "submenu":
        return any(
            child.block_type == "internal"
            and _page_is_within(page, child.value.get("page"))
            for child in item.value.get("links")
        )
    return False


# ---------------------------------------------------------------------------
# Social platform helpers
# ---------------------------------------------------------------------------

_SOCIAL_PLATFORM_LABELS = dict(SOCIAL_PLATFORM_CHOICES)

# Simple Icons SVG paths (24×24 viewBox, from https://simpleicons.org/ — CC0/public domain).
# Each value is the raw `d` attribute for the single <path> element.
_SOCIAL_ICONS = {
    "facebook": (
        "M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 "
        "11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 "
        "2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 "
        "3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"
    ),
    "twitter": (
        "M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.747"
        "l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"
    ),
    "instagram": (
        "M12 0C8.74 0 8.333.015 7.053.072 5.775.132 4.905.333 4.14.63c-.789.306-1.459.717"
        "-2.126 1.384S.935 3.35.63 4.14C.333 4.905.131 5.775.072 7.053.012 8.333 0 8.74 0 "
        "12c0 3.259.014 3.668.072 4.948.06 1.277.261 2.148.558 2.913.306.788.717 1.459 "
        "1.384 2.126.667.666 1.336 1.079 2.126 1.384.766.296 1.636.499 2.913.558C8.333 "
        "23.988 8.74 24 12 24c3.259 0 3.668-.014 4.948-.072 1.277-.06 2.148-.262 "
        "2.913-.558.788-.306 1.459-.718 2.126-1.384.666-.667 1.079-1.335 1.384-2.126.296"
        "-.765.499-1.636.558-2.913.06-1.28.072-1.689.072-4.948 0-3.259-.014-3.667-.072"
        "-4.947-.06-1.277-.262-2.149-.558-2.913-.306-.789-.718-1.459-1.384-2.126C21.319 "
        "1.347 20.651.935 19.86.63c-.765-.297-1.636-.499-2.913-.558C15.667.012 15.26 0 12 "
        "0zm0 2.16c3.203 0 3.585.016 4.85.071 1.17.055 1.805.249 2.227.415.562.217.96.477 "
        "1.382.896.419.42.679.819.896 1.381.164.422.36 1.057.413 2.227.057 1.266.07 "
        "1.646.07 4.85s-.015 3.585-.074 4.85c-.061 1.17-.256 1.805-.421 2.227-.224.562"
        "-.479.96-.899 1.382-.419.419-.824.679-1.38.896-.42.164-1.065.36-2.235.413-1.274"
        ".057-1.649.07-4.859.07-3.211 0-3.586-.015-4.859-.074-1.171-.061-1.816-.256"
        "-2.236-.421-.569-.224-.96-.479-1.379-.899-.421-.419-.69-.824-.9-1.38-.165-.42"
        "-.359-1.065-.42-2.235-.045-1.26-.061-1.649-.061-4.844 0-3.196.016-3.586.061"
        "-4.861.061-1.17.255-1.814.42-2.234.21-.57.479-.96.9-1.381.419-.419.81-.689 "
        "1.379-.898.42-.166 1.051-.361 2.221-.421 1.275-.045 1.65-.06 4.859-.06l.045.03zm0 "
        "3.678c-3.405 0-6.162 2.76-6.162 6.162 0 3.405 2.76 6.162 6.162 6.162 3.405 0 "
        "6.162-2.76 6.162-6.162 0-3.405-2.76-6.162-6.162-6.162zM12 16c-2.21 0-4-1.79-4-4s"
        "1.79-4 4-4 4 1.79 4 4-1.79 4-4 4zm7.846-10.405c0 .795-.646 1.44-1.44 1.44-.795 "
        "0-1.44-.646-1.44-1.44 0-.794.646-1.439 1.44-1.439.793-.001 1.44.645 1.44 1.439z"
    ),
    "tiktok": (
        "M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 "
        "1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 "
        "2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 "
        "3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01"
        "-1.49.18-2.16 1.13-4.2 2.65-5.65 1.54-1.48 3.67-2.31 5.81-2.24.02 1.48-.04 "
        "2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 "
        "1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4"
        "-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"
    ),
    "linkedin": (
        "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 "
        "1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 "
        "3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063"
        "-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 "
        "2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 "
        ".774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 "
        "22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
    ),
    "youtube": (
        "M23.495 6.205a3.007 3.007 0 0 0-2.088-2.088c-1.87-.501-9.396-.501-9.396-.501s"
        "-7.507-.01-9.396.501A3.007 3.007 0 0 0 .527 6.205a31.247 31.247 0 0 0-.522 "
        "5.805 31.247 31.247 0 0 0 .522 5.783 3.007 3.007 0 0 0 2.088 2.088c1.868.502 "
        "9.396.502 9.396.502s7.506 0 9.396-.502a3.007 3.007 0 0 0 2.088-2.088 31.247 "
        "31.247 0 0 0 .5-5.783 31.247 31.247 0 0 0-.5-5.805zM9.609 15.601V8.408l6.264 "
        "3.602z"
    ),
    "threads": (
        "M12.186 24h-.007c-3.581-.024-6.334-1.205-8.184-3.509C2.35 18.44 1.5 15.586 "
        "1.472 12.01v-.017c.03-3.579.879-6.43 2.525-8.482C5.852 1.205 8.6.024 12.18 0h"
        ".014c2.746.02 5.043.725 6.826 2.098 1.677 1.29 2.858 3.13 3.509 5.467l-2.04.569"
        "c-1.104-3.96-3.898-5.984-8.304-6.015-2.91.022-5.11.936-6.54 2.717C4.307 6.504 "
        "3.616 8.914 3.589 12c.027 3.086.718 5.496 2.057 7.164 1.43 1.783 3.631 2.698 "
        "6.54 2.717 2.623-.02 4.358-.631 5.689-2.044 1.34-1.43 2.079-3.607 2.103-6.199h"
        "-7.441v-2.103h9.569c.12.88.165 1.743.145 2.586-.06 3.896-1.199 6.895-3.288 "
        "8.864C17.063 23.237 14.858 24 12.186 24z"
    ),
    "bluesky": (
        "M12 10.8c-1.087-2.114-4.046-6.053-6.798-7.995C2.566.944 1.561 1.266.902 "
        "1.565.139 1.908 0 3.08 0 3.768c0 .69.378 5.65.624 6.479.815 2.736 3.713 3.66 "
        "6.383 3.364.136-.02.275-.039.415-.056-.138.022-.276.04-.415.056-3.912.58-7.387 "
        "2.005-2.83 7.078 5.013 5.19 6.87-1.113 7.823-4.308.953 3.195 2.05 9.271 7.733 "
        "4.308 4.267-4.308 1.172-6.498-2.74-7.078a8.741 8.741 0 0 1-.415-.056c.14.017.279"
        ".036.415.056 2.67.297 5.568-.628 6.383-3.364.246-.828.624-5.79.624-6.478 "
        "0-.69-.139-1.861-.902-2.206-.659-.298-1.664-.62-4.3 1.24C16.046 4.748 13.087 "
        "8.687 12 10.8z"
    ),
    "mastodon": (
        "M23.268 5.313c-.35-2.578-2.617-4.61-5.304-5.004C17.51.242 15.792 0 11.813 0h"
        "-.03c-3.98 0-4.835.242-5.288.309C3.882.692 1.496 2.518.917 5.127.64 6.412.61 "
        "7.837.661 9.143c.074 1.874.088 3.745.26 5.611.118 1.24.325 2.47.62 3.68.55 "
        "2.237 2.777 4.098 4.96 4.857 2.336.792 4.849.923 7.256.38.265-.061.527-.132.786"
        "-.213.585-.184 1.27-.39 1.774-.753a.057.057 0 0 0 .023-.043v-1.809a.052.052 0 0 "
        "0-.02-.041.053.053 0 0 0-.046-.01 20.282 20.282 0 0 1-4.709.545c-2.73 0-3.463"
        "-1.284-3.674-1.818a5.593 5.593 0 0 1-.319-1.433.053.053 0 0 1 .066-.054c1.517.363 "
        "3.072.546 4.632.546.376 0 .75 0 1.125-.01 1.57-.044 3.224-.124 4.768-.422.038"
        "-.008.077-.015.11-.024 2.435-.464 4.753-1.92 4.989-5.604.008-.145.03-1.52.03"
        "-1.67.002-.512.167-3.63-.024-5.545zm-3.748 9.195h-2.561V8.29c0-1.309-.55-1.976"
        "-1.67-1.976-1.23 0-1.846.79-1.846 2.35v3.403h-2.546V8.663c0-1.56-.617-2.35"
        "-1.848-2.35-1.112 0-1.668.668-1.67 1.977v6.218H4.822V8.102c0-1.31.337-2.35 "
        "1.011-3.12.696-.77 1.608-1.164 2.74-1.164 1.311 0 2.302.5 2.962 1.498l.638 "
        "1.06.638-1.06c.66-.999 1.65-1.498 2.96-1.498 1.13 0 2.043.395 2.74 1.164.675.77 "
        "1.012 1.81 1.012 3.12z"
    ),
    "whatsapp": (
        "M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15"
        "-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255"
        "-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458"
        ".13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198"
        ".05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5"
        "-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297"
        "-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 "
        "5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571"
        "-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124"
        "-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l"
        "-.361-.214-3.741.982.999-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001"
        "-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 "
        "0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 "
        "11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 "
        "1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c"
        "6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413"
    ),
}

# Fallback: generic external link icon (Heroicons outline)
_SOCIAL_ICON_DEFAULT = (
    "M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 "
    "0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
)


@register.simple_tag
def social_icon(platform):
    """
    Render an inline SVG icon for the given social platform slug.

    Returns a safe HTML string containing a 24×24 SVG. Falls back to a
    generic link icon if the platform is not recognised.

    Usage in templates:
        {% load wtrx_tags %}
        {% social_icon "facebook" %}
    """
    path_d = _SOCIAL_ICONS.get(platform, _SOCIAL_ICON_DEFAULT)
    return format_html(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'fill="currentColor" width="20" height="20" aria-hidden="true">'
        '<path d="{}"/>'
        "</svg>",
        path_d,
    )


@register.filter
def social_platform_label(platform):
    """
    Return the human-readable label for a social platform slug.

    Usage in templates:
        {% load wtrx_tags %}
        {{ "facebook"|social_platform_label }}  {# → "Facebook" #}
    """
    return _SOCIAL_PLATFORM_LABELS.get(platform, platform)


@register.simple_tag
def page_as_card(page):
    """
    Convert a Wagtail Page object into the card dict shape expected by
    components/card.html.

    card.html expects: heading, description, image, link_page, link_url.
    Wagtail Page objects have: title, search_description, and optionally
    hero_image (if the page uses HeroMixin).

    Usage in templates:
        {% load wtrx_tags %}
        {% page_as_card child as card %}
        {% include "components/card.html" %}
    """
    image = getattr(page, "hero_image", None)
    return {
        "heading": page.title,
        "description": page.search_description or "",
        "image": image,
        "link_page": page,
        "link_url": None,
    }


# ---------------------------------------------------------------------------
# Structured data (JSON-LD)
# ---------------------------------------------------------------------------


@register.simple_tag(takes_context=True)
def organization_structured_data(context):
    """
    Render a <script type="application/ld+json"> Organization entry for
    search engines (Google Knowledge Panel, sitelinks, etc.), built entirely
    from existing Branding & SEO / Social settings data — no dedicated
    structured-data fields to keep in sync.

    Usage in templates:
        {% load wtrx_tags %}
        {% organization_structured_data %}

    Returns an empty string if there's no site to resolve for the request.
    """
    request = context.get("request")
    if request is None:
        return ""

    site = Site.find_for_request(request)
    if site is None:
        return ""

    branding = BrandingSEOSettings.for_request(request)
    social = SocialSettings.for_request(request)

    data = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": site.site_name or site.hostname,
        "url": request.build_absolute_uri("/"),
    }
    if branding.site_description:
        data["description"] = branding.site_description
    if branding.logo:
        rendition = branding.logo.get_rendition("max-600x600")
        data["logo"] = request.build_absolute_uri(rendition.url)

    same_as = [item.value["url"] for item in social.social_links if item.value["url"]]
    if same_as:
        data["sameAs"] = same_as

    json_str = json.dumps(data, cls=DjangoJSONEncoder).translate(_json_script_escapes)
    return mark_safe(f'<script type="application/ld+json">{json_str}</script>')


@register.filter
def absolute_uri(url, request):
    """
    Resolve `url` to an absolute URL against `request`.

    Needed because Django template syntax can't pass an argument to
    `request.build_absolute_uri` (`{{ request.build_absolute_uri }}` calls
    it with zero args, returning the *current page's* URL, not the given
    one). Calling it properly, as here, handles both storage backends
    correctly: a relative path (local filesystem storage, e.g.
    "/media/images/foo.jpg") resolves against the request's own scheme and
    host; a URL that's already absolute (S3/CDN-backed storage in
    production) is returned unchanged rather than getting a second
    scheme+host prepended in front of it.

    Usage in templates:
        {% load wtrx_tags %}
        <meta property="og:image" content="{{ og_img.url|absolute_uri:request }}" />
    """
    if not url:
        return url
    return request.build_absolute_uri(url)

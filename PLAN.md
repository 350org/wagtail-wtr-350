# wagtail-wtr: Implementation Plan

## Overview

wagtail-wtr is the Wagtail CMS platform used at With the Ranks for campaign,
nonprofit, and organizer websites. New client sites fork or clone this repo.

**Target users (MVP)**: Developers at With the Ranks who spin up new campaign/nonprofit
sites. They want to get 80% done fast, then theme and add site-specific functionality.

**Eventual goal**: Extract `wtrx/` to a standalone pip package (`wagtail-wtrx`),
following the CodeRed CMS pattern. The package will provide base classes; site apps
provide thin concrete subclasses.

---

## Architecture

This is a standard Django project. `wagtail_wtr/` is the project config package
(settings, urls, wsgi only). `wtrx/` is the core reusable app — client sites don't
edit it, they extend/override. New sites fork this repo; the `wagtail_wtr` package
name stays as-is but `wtrx/` is a top-level sibling, not nested inside it.

```
wagtail-wtr/
├── wtrx/                               # Core reusable app (DON'T EDIT on client sites)
│   ├── __init__.py
│   ├── apps.py
│   ├── blocks/
│   │   ├── __init__.py                 # Exports BodyStreamBlock, SectionContentBlock
│   │   ├── content.py                  # TextBlock, ImageBlock, VideoBlock, ButtonBlock,
│   │   │                               #   QuoteBlock, RawHTMLBlock, TableBlock
│   │   ├── layout.py                   # SectionBlock, CardGridBlock, AccordionBlock
│   │   ├── composite.py                # CalloutBlock, HeroBlock
│   │   ├── cards.py                    # CardBlock, PersonCardBlock
│   │   └── actions.py                  # DonateBlock, SignupBlock variants
│   ├── models.py                       # BasePage, HeroMixin, HomePage, ContentPage,
│   │                                   #   IndexPage, FormField, FormPage
│   ├── views.py                        # search() view
│   ├── site_settings.py                # BrandingSEOSettings, NavigationSettings,
│   │                                   #   FooterSettings, SocialSettings, IntegrationSettings
│   ├── images.py                       # CustomImage, Rendition
│   ├── templatetags/
│   │   ├── __init__.py
│   │   └── wtrx_tags.py
│   ├── wagtail_hooks.py
│   ├── migrations/
│   └── management/
│       └── commands/
│           └── setup_site.py           # Interactive setup command
├── wagtail_wtr/                        # Django project package (settings, urls, wsgi only)
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── production.py
│   ├── __init__.py
│   ├── urls.py
│   └── wsgi.py
├── templates/
│   ├── base.html
│   ├── base_page.html
│   ├── 404.html
│   ├── 500.html
│   ├── navigation/
│   │   ├── header.html
│   │   └── footer.html
│   ├── components/
│   │   ├── hero.html
│   │   ├── button.html
│   │   ├── card.html
│   │   ├── person_card.html
│   │   ├── pagination.html
│   │   ├── language_switcher.html
│   │   └── streamfield/
│   │       └── blocks/
│   │           ├── text_block.html
│   │           ├── image_block.html
│   │           ├── video_block.html
│   │           ├── button_block.html
│   │           ├── quote_block.html
│   │           ├── raw_html_block.html
│   │           ├── table_block.html
│   │           ├── section_block.html
│   │           ├── card_grid_block.html
│   │           ├── accordion_block.html
│   │           ├── callout_block.html
│   │           ├── hero_block.html
│   │           ├── card_block.html
│   │           ├── person_card_block.html
│   │           ├── donate_block.html
│   │           └── signup_block.html
│   └── pages/
│       ├── home_page.html
│       ├── content_page.html
│       ├── index_page.html
│       └── form_page.html
├── static_src/
│   ├── javascript/
│   │   ├── main.js
│   │   └── components/
│   │       ├── mobile-menu.js
│   │       ├── accordion.js         # Accordion toggle with aria-expanded
│   │       └── form-ajax.js        # AJAX form submission for FormPage/SignupBlock
│   └── css/
│       ├── main.css                # Tailwind entry point — imports theme.css + tailwindcss
│       └── theme.css               # Client-editable: @theme {} tokens + [data-theme] presets
├── static_compiled/                # Tailwind CLI output (committed)
├── fixtures/
│   └── demo.json
├── package.json
├── pyproject.toml                  # Python dependencies and project metadata
├── manage.py
├── Dockerfile
├── Makefile
├── .gitignore
├── .dockerignore
├── .nvmrc
└── LICENSE
```

**Total files**: ~75-80 files

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Project structure | Working Django project, not a `wagtail start --template` | Developers can run `manage.py` directly; no token round-tripping for migrations |
| New client sites | Fork/clone this repo | Sites keep `wagtail_wtr` package name; site-specific code lives in new apps outside `wtrx/` |
| Reusable app | `wtrx/` at repo root (sibling to `wagtail_wtr/`) | Clean separation: `wagtail_wtr/` is project config only; `wtrx/` is the pip-extractable app |
| Concrete page models | All page models (`HomePage`, `ContentPage`, `IndexPage`, `FormPage`) live in `wtrx/` | Simplifies the fork model — no thin proxy apps needed. Forks add new page types in new apps. |
| Future pip package | `wagtail-wtrx` (CodeRed pattern) | Package ships concrete models; forks extend with new page types in separate apps. Extraction happens when wtrx is stable. |
| CSS framework | Tailwind CSS v4 with semantic design tokens | `bg-primary`, `font-heading`, etc. Sites customize via `@theme {}` block in `static_src/css/theme.css`. No raw color values in templates. |
| Dark mode | No (post-MVP) | Reduces CSS complexity |
| Multi-lingual | Yes, via `wagtail-localize` | i18n infrastructure from day one. Sites default to English, add languages as needed. |
| Layout philosophy | Opinionated composite blocks, no raw columns | Editors can't break layouts |
| Hero | HeroMixin on pages + HeroBlock in StreamField | Dedicated hero at top of page + mid-page hero sections |
| Page title / h1 | Page title is the h1. `hero_headline` overrides if set. | Every page gets an h1 automatically |
| Form submission | AJAX | Form stays on page, thank-you text replaces form on success |
| Platform integrations | Site-wide settings, defaults from `settings.py`, overridable in admin | One configuration point, not per-block |
| Block field visibility | All SignupBlock variants always registered; irrelevant ones hidden via `wagtail_hooks.py` based on `IntegrationSettings` | Avoids DB access at import time |
| Frontend build | Tailwind CLI (no webpack, no PostCSS config, no Sass) | Simpler pipeline, fewer deps, same semantic token output |
| Settings panels | 5 clear panels under Settings | Each panel has a clear purpose, no grab-bags |
| Python deps | `pyproject.toml` | Modern Python packaging standard |

---

## Block Inventory (15 blocks)

### Content Blocks (7)

**1. TextBlock**
- Type: RichTextBlock (no StructBlock wrapper)
- Features: bold, italic, link, ol, ul, h2, h3, h4
- (value) **required**

**2. ImageBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| image | ImageChooserBlock | **Yes** |
| alt_text | CharBlock | No |
| caption | CharBlock | No |

**3. VideoBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| embed_url | URLBlock | **At least one of embed_url or media_file** |
| media_file | VideoChooserBlock (from `wagtailmedia.blocks`) | **At least one of embed_url or media_file** |
| caption | CharBlock | No |

Custom `clean()` enforces exactly one of `embed_url` or `media_file`.
`VideoChooserBlock` returns a `wagtailmedia.Media` instance. The template uses
`<video>` tags with `value.sources` for file-based video, and an `<iframe>` /
embed for `embed_url`.

**4. ButtonBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| text | CharBlock | **Yes** |
| link_page | PageChooserBlock | **Exactly one of link_page or link_url** |
| link_url | URLBlock | **Exactly one of link_page or link_url** |
| style | ChoiceBlock (primary/secondary/outline) | No, default: primary |

Custom `clean()` enforces exactly one link field.

**5. QuoteBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| quote | TextBlock (plain) | **Yes** |
| attribution | CharBlock | No |
| title | CharBlock | No |

**6. RawHTMLBlock**
- Type: RawHTMLBlock (no wrapper)
- (value) **required**

**7. TableBlock**
- Type: wagtail.contrib.table_block.TableBlock (no wrapper)
- (value) **required**

### Layout Blocks (3)

**8. SectionBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| content | StreamBlock (all blocks except SectionBlock) | **Yes** |
| background | ChoiceBlock (light/dark/primary/muted) | No, default: light |
| padding | ChoiceBlock (sm/md/lg) | No, default: md |
| anchor_id | CharBlock | No |

No heading field — editors use h2 in a TextBlock inside the content.

**9. CardGridBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| cards | ListBlock(CardBlock), min 2, max 12 | **Yes** |

Auto-responsive columns. No heading, no column selection.

**10. AccordionBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| items | ListBlock(AccordionItemBlock), min 1 | **Yes** |
| -- title | CharBlock | **Yes** |
| -- content | RichTextBlock | **Yes** |

`AccordionItemBlock` is an explicitly named `StructBlock` subclass (not anonymous).

No heading.

### Composite Blocks (2)

**11. CalloutBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| content | RichTextBlock | **Yes** |
| image | ImageChooserBlock | **Yes** |
| link_text | CharBlock | No |
| link_page | PageChooserBlock | No |
| link_url | URLBlock | No |
| alignment | ChoiceBlock (image-left/image-right) | No, default: image-left |

Image + rich text side by side. Stacks on mobile.

Custom `clean()` validates at most one of `link_page` or `link_url` is set.

**12. HeroBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| content | RichTextBlock | **Yes** |
| image | ImageChooserBlock | No |
| link_text | CharBlock | No |
| link_page | PageChooserBlock | No |
| link_url | URLBlock | No |

Mid-page hero section. Uses RichTextBlock so editors can use h2/h3 for headings within.

Custom `clean()` validates at most one of `link_page` or `link_url` is set
(same validation as CalloutBlock).

### Card Blocks (2)

**13. CardBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| icon | ImageChooserBlock | No |
| heading | CharBlock | **Yes** |
| description | TextBlock (plain) | No |
| image | ImageChooserBlock | No |
| link_page | PageChooserBlock | No |
| link_url | URLBlock | No |

Optional icon image displayed beside the heading. Rendered at 24x24px with
`alt=""` (decorative). When omitted, the heading renders without any icon.

**14. PersonCardBlock** (StructBlock)

| Field | Type | Required |
|---|---|---|
| name | CharBlock | **Yes** |
| role | CharBlock | No |
| image | ImageChooserBlock | No |
| bio | TextBlock (plain) | No |
| email | EmailBlock | No |
| phone | CharBlock | No |
| website | URLBlock | No |

### Action Blocks (dynamically registered)

**15a. DonateBlock** (StructBlock) — single variant, behavior from IntegrationSettings

| Field | Type | Required |
|---|---|---|
| heading | CharBlock | **Yes** |
| description | RichTextBlock | No |
| button_text | CharBlock | No, default: "Donate" |
| override_amounts | ListBlock(IntegerBlock) | No |
| override_url | URLBlock | No |

**15b. SignupBlock -- wagtail_forms variant** (StructBlock)

| Field | Type | Required |
|---|---|---|
| heading | CharBlock | **Yes** |
| description | RichTextBlock | No |
| button_text | CharBlock | No, default: "Sign Up" |
| form_page | PageChooserBlock | **Yes** |
| success_message | CharBlock | No |

Renders the FormPage's form inline. AJAX submission. The block template fetches
the form instance via a template tag: call `form_page_value.get_form_class()()`
to instantiate an unbound form, and pass it to the template context.
AJAX handler submits to `form_page.url`.

**15c. SignupBlock -- action_network variant** (StructBlock)

| Field | Type | Required |
|---|---|---|
| heading | CharBlock | **Yes** |
| description | RichTextBlock | No |
| action_url | URLBlock | **Yes** |
| success_message | RichTextBlock | No |

Editor pastes a full Action Network URL (e.g.
`https://actionnetwork.org/forms/join-30?source=direct_link&`). The block
auto-extracts the action type and slug via `parse_action_network_url()`, then
renders the v6 JS embed widget with fully custom CSS styling (no AN CSS loaded).
All form styles are scoped under `.wtr-action-network-embed` using the project's
design tokens. When `success_message` is provided, a MutationObserver detects
AN's `.can_thank_you_wrap` element and replaces it with the custom message.
Only `/forms/` URLs are supported initially; other AN action types can be added
by extending the `ACTION_NETWORK_URL_TYPES` dict.

**15d. SignupBlock -- none/link variant** (StructBlock)

| Field | Type | Required |
|---|---|---|
| heading | CharBlock | **Yes** |
| description | RichTextBlock | No |
| button_text | CharBlock | No, default: "Sign Up" |
| external_url | URLBlock | **Yes** |

Simple link-out CTA.

The correct SignupBlock variant is shown to editors via `wagtail_hooks.py`, which
reads `IntegrationSettings` at request time (not at import/class-definition time)
and hides irrelevant block types in the Wagtail editor interface. All variants are
always registered in `BodyStreamBlock` — hiding is purely a UI concern.

---

## Page Types (4)

### HomePage
- **Inherits**: BasePage + HeroMixin
- **Fields**: body (BodyStreamBlock), use_transparent_header (BooleanField)
- **Template**: `pages/home_page.html`
- **Parent**: Root (Site root page)
- **Notes**: Hero at top (from HeroMixin), StreamField body below.
  `use_transparent_header=True` makes the header `position:absolute` so the hero
  image extends behind it; automatically uses `BrandingSEOSettings.dark_logo` if set.

### ContentPage
- **Inherits**: BasePage + HeroMixin
- **Fields**: body (BodyStreamBlock)
- **Template**: `pages/content_page.html`
- **Parent**: Any page
- **Notes**: General purpose content page

### IndexPage
- **Inherits**: BasePage + HeroMixin
- **Fields**: intro (RichTextField, optional), body (BodyStreamBlock, optional)
- **Template**: `pages/index_page.html`
- **Parent**: Any page
- **Notes**: Auto-lists child pages in a card grid with pagination. Child page
  query: `get_children().live().public().specific().order_by('title')`.
  Draft and private pages are excluded. All child page types are shown (no
  type filter). Optional StreamField body below the listing.

### FormPage
- **Inherits**: `class FormPage(BasePage, AbstractEmailForm)` — BasePage first for correct MRO
- **Panels**: Must explicitly define `content_panels` starting from
  `AbstractEmailForm.content_panels` (which equals `Page.content_panels`) and
  adding all form-specific panels. Do NOT rely on MRO inheritance alone, as
  Python's MRO would resolve to `BasePage.content_panels` and drop the email fields:
  ```python
  content_panels = AbstractEmailForm.content_panels + [
      FieldPanel("intro"),
      InlinePanel("form_fields", label="Form fields"),
      FieldPanel("thank_you_text"),
      MultiFieldPanel([
          FieldPanel("to_address"),
          FieldPanel("from_address"),
          FieldPanel("subject"),
      ], heading="Email notifications"),
  ]
  # promote_panels: BasePage.promote_panels (meta_image, hide_from_search)
  # is inherited correctly via MRO — no explicit merge needed there.
  ```
- **Required companion model** in `forms/models.py`:
  ```python
  class FormField(AbstractFormField):
      page = ParentalKey(
          "FormPage",
          on_delete=models.CASCADE,
          related_name="form_fields",
      )
  ```
  `AbstractFormField` is from `wagtail.contrib.forms.models`. The
  `related_name="form_fields"` must match what `get_form_fields()` expects.
- **Fields**: intro (RichTextField), form fields (Wagtail form builder),
  thank_you_text (RichTextField), email subject/from/to
- **Template**: `pages/form_page.html`
- **Parent**: Any page
- **Notes**: AJAX submission. Form replaced with thank_you_text on success. Also
  used by SignupBlock (wagtail_forms variant) for inline form rendering.
- **Future: platform forwarding** — `process_form_submission()` is the correct
  override point for forwarding submissions to Action Network (or other platforms).
  When `IntegrationSettings.signup_platform == "action_network"`, override this
  method to POST cleaned form data to the Action Network API using
  `IntegrationSettings.action_network_api_key`. Field mapping (email → email,
  first_name, last_name, zip, etc.) and an optional `action_network_action_id`
  field on `FormPage` will be needed. A `FormMixin` in `wtrx/` is the clean
  abstraction for this — keeps the AN forwarding logic in the extractable package.
  Error handling: log API failures and continue (don't block the user's submission).
  Not implemented in Phase 3 — no architectural changes to Phase 3 required.

---

## Core Models & Mixins

### BasePage (abstract)

`BasePage` must NOT include `TranslatableMixin` explicitly. In Wagtail 7,
`TranslatableMixin` is already in `Page.__mro__` via `AbstractPage`. Adding it
again causes `TypeError: Cannot create a consistent MRO`. Use:

```python
class BasePage(Page):
    ...
```

`wagtail-localize` correctly detects `BasePage` as translatable because
`TranslatableMixin in BasePage.__mro__` is `True` through the inherited chain.

| Field | Type | Notes |
|---|---|---|
| meta_image | ForeignKey to CustomImage | On promote_panels. Fallback to BrandingSEOSettings.default_meta_image |
| hide_from_search | BooleanField | Toggle visibility in search results (used in `BasePage.get_sitemap_urls()`) |

### HeroMixin (abstract)

| Field | Type | Notes |
|---|---|---|
| hero_headline | CharField | Optional. Overrides page title as displayed h1. |
| hero_copy | RichTextField | Optional. Subtext below headline. |
| hero_image | ForeignKey to CustomImage | Optional. Hero background/feature image. Also used as video poster fallback. |
| hero_video | ForeignKey to wagtailmedia.Media | Optional. When set, hero switches to two-column layout (text left, video right). |
| hero_link_text | CharField | Optional. CTA button text. |
| hero_link_page | ForeignKey to Page | Optional. CTA internal link. |
| hero_link_url | URLField | Optional. CTA external link. |

### CustomImage
- Extends `AbstractImage`
- Custom `Rendition` extending `AbstractRendition`
- `object_position_style` property for focal point CSS

---

## Site Settings (5 panels)

### Settings > Branding & SEO (`BrandingSEOSettings`)

| Field | Type | Required |
|---|---|---|
| logo | ForeignKey to CustomImage | No |
| dark_logo | ForeignKey to CustomImage | No |
| favicon | ForeignKey to CustomImage | No |
| default_meta_image | ForeignKey to CustomImage | No |
| site_description | TextField | No |

### Settings > Navigation (`NavigationSettings`)

| Field | Type | Required |
|---|---|---|
| primary_navigation | StreamField (InternalLinkBlock, ExternalLinkBlock, AnchorLinkBlock) | No |
| cta_text | CharField | No |
| cta_page | ForeignKey to Page | No |
| cta_url | URLField | No |
| cta_anchor | CharField | No — anchor ID (no #) for same-page CTA link |
| collapse_desktop_menu | BooleanField | No, default False — always show hamburger icon |

### Settings > Footer (`FooterSettings`)

| Field | Type | Required |
|---|---|---|
| layout | CharField (choices: columns, minimal) | No, default: columns |
| footer_navigation | StreamField (FooterColumnBlock: heading + links) | No — used by columns layout |
| minimal_links | StreamField (InternalLinkBlock, ExternalLinkBlock, AnchorLinkBlock) | No — used by minimal layout |
| copyright_text | CharField | No, falls back to "(c) {year} {site name}" |

**Columns layout**: multi-column navigation grid, logo at top, social links + copyright in bottom bar.
**Minimal layout**: single row — `[logo + copyright] [social icons] [inline links]`, stacking on mobile.

### Settings > Social (`SocialSettings`)

| Field | Type | Required |
|---|---|---|
| social_links | StreamField of SocialLinkBlock (platform: ChoiceBlock, url: URLBlock) | No |
| show_in_header | BooleanField | No, default False — show social icons in header menu panel |
| show_in_footer | BooleanField | No, default True — show social icons in footer |

`SocialLinkBlock` is an explicitly named `StructBlock` subclass. Use a `StreamField`,
not a `ListBlock`, so each item is independently typed and editable in the admin.

Platform choices: Facebook, Twitter/X, Instagram, TikTok, LinkedIn, YouTube, Threads,
Bluesky, Mastodon

### Settings > Integrations (`IntegrationSettings`)

| Field | Type | Required |
|---|---|---|
| donation_platform | CharField (choices: none, actblue) | No, default from `WTRX_DONATION_PLATFORM` |
| donation_base_url | URLField | No |
| donation_suggested_amounts | CharField | No, comma-separated integers (e.g., "10,25,50,100"). Parse in templates/views with `[int(x) for x in amounts.split(",") if x.strip()]`. |
| donation_default_recurring | BooleanField | No, default: False |
| signup_platform | CharField (choices: wagtail_forms, action_network, none) | No, default from `WTRX_SIGNUP_PLATFORM` |
| action_network_api_key | CharField | No |

Note: `DonateBlock.override_amounts` uses `ListBlock(IntegerBlock)` (already a Python list).
`IntegrationSettings.donation_suggested_amounts` uses a `CharField` (comma-separated string)
for simpler admin UI. The template/view layer must parse the CharField when using it.

---

## Django Settings

```python
# settings/base.py
WTRX_DONATION_PLATFORM = "none"           # none, actblue
WTRX_SIGNUP_PLATFORM = "wagtail_forms"    # wagtail_forms, action_network, none

# Internationalization
USE_I18N = True
WAGTAIL_I18N_ENABLED = True
LANGUAGE_CODE = "en"
WAGTAIL_CONTENT_LANGUAGES = LANGUAGES = [
    ("en", "English"),
    # Sites add languages as needed:
    # ("es", "Spanish"),
    # ("fr", "French"),
]
```

`WTRX_*` defaults are overridable in Wagtail admin via IntegrationSettings.
Language configuration is in `settings/base.py` — sites uncomment or add
languages to `WAGTAIL_CONTENT_LANGUAGES`.

### Required INSTALLED_APPS entries (non-obvious ones)

```python
INSTALLED_APPS = [
    # ... standard Django + Wagtail apps ...
    "wagtail.contrib.forms",        # Required for FormPage / AbstractEmailForm
    "wagtail.contrib.table_block",  # Required for TableBlock
    "wagtail.contrib.redirects",
    "wagtail.contrib.settings",     # Required for site settings models
    "wagtail.contrib.frontend_cache",  # Required for CDN cache invalidation
    "wagtail.locales",              # Required for locale management UI (wagtail-localize)
    "wagtail_localize",             # Required for i18n support
    "wagtailmedia",                 # Required for VideoBlock (VideoChooserBlock)
    # ... project apps ...
]
```

---

## Template Hierarchy

```
base.html
  -- <html>, <head>, <body>, loads CSS/JS
  -- Blocks: title, meta_description, extra_head, header, content, footer, extra_js
  -- Loads BrandingSEOSettings for favicon, meta defaults

  base_page.html (extends base.html)
    -- Includes navigation/header.html (reads NavigationSettings)
    -- Includes navigation/footer.html (reads FooterSettings, SocialSettings)
    -- Blocks: hero, above_content, content, below_content

    pages/home_page.html (extends base_page.html)
      -- Renders hero (from HeroMixin via components/hero.html)
      -- Renders body StreamField

    pages/content_page.html (extends base_page.html)
      -- Renders hero (from HeroMixin via components/hero.html)
      -- Renders body StreamField

    pages/index_page.html (extends base_page.html)
      -- Renders hero (from HeroMixin via components/hero.html)
      -- Renders intro
      -- Auto-lists child pages as cards with pagination
      -- Renders optional body StreamField

    pages/form_page.html (extends base_page.html)
      -- Renders hero (page title as h1)
      -- Renders intro
      -- Renders form (AJAX submission)
      -- Thank-you text replaces form on success
```

### Header (`navigation/header.html`)
- Logo left (from BrandingSEOSettings.logo; uses dark_logo when transparent header active)
- Nav links right (from NavigationSettings.primary_navigation — InternalLink, ExternalLink, AnchorLink)
- CTA button right (from NavigationSettings.cta_text/cta_page/cta_url/cta_anchor)
- Social icons in menu panel (from SocialSettings when show_in_header=True)
- Collapsed desktop menu option (NavigationSettings.collapse_desktop_menu) — hides desktop nav, shows hamburger at all breakpoints
- Transparent header option (HomePage.use_transparent_header) — absolute position, transparent bg, light text colors
- Mobile: logo left, hamburger right. Hamburger opens nav panel (same JS, breakpoint-agnostic).

### Footer (`navigation/footer.html`)
- **Columns layout** (default): logo at top, multi-column navigation grid (FooterSettings.footer_navigation), social links + copyright in bottom bar
- **Minimal layout**: single row — `[logo + copyright] [social icons] [inline links]`
- Social icons guarded by SocialSettings.show_in_footer (default True)
- Copyright line (from FooterSettings.copyright_text, fallback: "(c) {year} {site name}")

### Hero (`components/hero.html`)
- h1: `hero.headline` — always set by `get_context()` (falls back to `page.title` there, not in template)
- Subtext: `hero.copy` (rendered via `|richtext` filter when `hero.copy_is_block=False`)
- Image: `hero.image`
- Video: `hero.video` (wagtailmedia Media instance) — when set, switches to two-column layout
- CTA button: `hero.link_text` + `hero.link_page`/`hero.link_url`
- Same template used by all page types and by `HeroBlock` (mid-page; video always None)

**Context contract**: the template consumes a `hero` dict with keys:
`headline`, `copy`, `copy_is_block`, `image`, `video`, `link_text`, `link_page`, `link_url`.
Both `HeroBlock.get_context()` (Phase 2) and `HeroMixin` page `get_context()`
(Phase 3) MUST build this dict. For both, `copy_is_block=False` because `copy`
is either a `RichTextBlock` value or a `RichTextField` string — both use `|richtext`.

**Video layout**: when `hero.video` is present, the template renders a two-column
responsive grid (text left/right-aligned on md+, video right). On mobile both
columns are full-width, video below text. Background image overlay is suppressed.
Poster fallback chain: wagtailmedia thumbnail → `hero.image` at `fill-1280x720` → no poster.

HTML templates use standard Django template syntax. No special wrappers needed.

---

## Frontend Build

### Stack
- **Tailwind CSS v4** via `@tailwindcss/cli`
- **Vanilla JS** served directly (no bundler)

### Theming — `static_src/css/theme.css`

In Tailwind v4 there is no `tailwind.config.js`. All theme customisation lives
in `static_src/css/theme.css`, which is imported by `main.css` before Tailwind
processes utilities:

```css
/* main.css */
@import './theme.css';
@import 'tailwindcss';

@plugin '@tailwindcss/typography';
@plugin '@tailwindcss/forms';
```

```css
/* theme.css */
@theme {
  /* Semantic color tokens — replace these to re-theme the site */
  --color-primary-50:  #f0f9ff;
  --color-primary-500: #0ea5e9;
  --color-primary-600: #0284c7;
  /* ... full scale 50–950 ... */

  --color-secondary-600: #7c3aed;
  /* ... */

  --color-accent-500: #f97316;
  /* ... */

  --color-neutral-50:  #fafafa;
  /* ... */

  /* Status tokens — used for error, success, warning UI */
  --color-error-600:   #dc2626;
  --color-success-600: #16a34a;
  --color-warning-600: #d97706;

  /* Font stacks */
  --font-heading: system-ui, sans-serif;
  --font-body:    system-ui, sans-serif;
}

/* Named preset — overrides at runtime via <html data-theme="grassroots"> */
[data-theme="grassroots"] {
  --color-primary-500: #22c55e;
  /* ... */
}
```

All templates use only semantic tokens (`bg-primary-600`, `font-heading`, etc.),
so changing the `@theme {}` values and running `make build` re-themes the entire site.
Named `[data-theme]` presets override tokens at runtime — no rebuild needed.

### npm scripts

```json
{
  "build":      "tailwindcss -i ./static_src/css/main.css -o ./static_compiled/css/main.css",
  "build:prod": "tailwindcss -i ./static_src/css/main.css -o ./static_compiled/css/main.css --minify",
  "start":      "tailwindcss -i ./static_src/css/main.css -o ./static_compiled/css/main.css --watch"
}
```

### Output
`static_src/css/main.css` → Tailwind CLI → `static_compiled/css/main.css` (committed to repo)
`static_src/javascript/` → copied to `static_compiled/js/` via `make build-js` (committed to repo)

---

## Python Dependencies (pyproject.toml)

```
django>=5.2,<5.3           # Django 5.2 LTS
wagtail>=7.0,<8.0          # Wagtail 7.0 LTS
wagtail-localize
wagtailmedia
modelsearch                # Required by Wagtail 7.3 (extracted from wagtail.search)
dj-database-url
psycopg[binary]
whitenoise
gunicorn
django-storages[s3]
wagtail-storages
```

Dev extras:

```
[project.optional-dependencies]
dev = [
    "coverage",
    "django-debug-toolbar",
    "factory-boy",
    "wagtail-factories",
]
```

## Node Dependencies

```
tailwindcss              # v4 CSS framework
@tailwindcss/cli         # v4 CLI binary (installs the `tailwindcss` command)
@tailwindcss/typography  # prose classes for richtext
@tailwindcss/forms       # base form element styling
```

---

## Management Commands

### `setup_site`

Interactive command run after cloning/forking the repo:

```
$ make setup
Site name: My Campaign
Site language (default: en) [en]:
Donation platform (none/actblue) [none]: actblue
ActBlue donation URL: https://secure.actblue.com/donate/mycampaign
Suggested donation amounts [10,25,50,100]:
Signup platform (wagtail_forms/action_network/none) [wagtail_forms]:
```

Creates initial Site object, `HomePage` instance (placed at the Wagtail page tree
root), SiteSettings records, and optionally loads demo fixtures. Creating the
`HomePage` requires inserting it into the Wagtail page tree programmatically
(not just `HomePage.objects.create()`), using `root_page.add_child(instance=home)`.

---

## Implementation Phases

### ✅ Phase 0: Project Scaffolding — COMPLETE (commits 78333b5, 7112e0f, 91e730c)
- Directory structure, `manage.py`, `settings/`, `urls.py`, `wsgi.py`
- `pyproject.toml` (Python 3.13, Django 5.2 LTS, Wagtail 7.0 LTS)
- `package.json`, `tailwind.config.js`, `Dockerfile`, `Makefile`, `.gitignore`
- `wtrx/` app skeleton, `users/` app with custom User model + migration (later removed — see Phase 9)
- `search/` app with search view (Query/add_hit removed — dropped in Wagtail 7.0)
- Base templates (`base.html`, `base_page.html`, `404.html`, `500.html`)
- `WAGTAILADMIN_BASE_URL` in `dev.py`/`production.py` (not `base.py`)
- Originally scaffolded as `wagtail start --template`; 15/15 tests passed

### ✅ Phase 1: Core Models & Settings — COMPLETE (commit 0db0df6)
- [x] `wtrx/images.py` -- CustomImage + CustomRendition models, `credit` field
- [x] `wtrx/models.py` -- BasePage (`class BasePage(Page)` — no TranslatableMixin), HeroMixin
- [x] `wtrx/site_settings.py` -- all 5 settings panels + InternalLinkBlock,
  ExternalLinkBlock, FooterColumnBlock, SocialLinkBlock
- [x] `wtrx/templatetags/wtrx_tags.py` -- tag library stub (settings accessed via context processor)
- [x] `WAGTAILIMAGES_IMAGE_MODEL` uncommented in `settings/base.py`
- [x] Migrations generated and verified
- [x] Agent code review (issues addressed)
- [x] Human code review
- [x] Commit

### ✅ Refactor: Template → Working Project — COMPLETE
- [x] Renamed `project_name/` → `wagtail_wtr/`
- [x] Replaced all `{{ project_name }}` tokens with `wagtail_wtr`
- [x] Removed `{% verbatim %}` wrappers from all HTML templates
- [x] Regenerated migrations directly (no test site round-trip needed)
- [x] Updated AGENTS.md, PLAN.md, README.md, .gitignore, pyproject.toml

### ✅ Phase 2: StreamField Blocks — COMPLETE (commit 28e0d1c)
- [x] All 18 blocks consolidated in `wtrx/blocks/__init__.py` (single file)
- [x] `ACTION_NETWORK_ACTION_TYPE_CHOICES` + `action_type` field on `SignupActionNetworkBlock`
- [x] `HeroBlock.get_context()` normalises fields into `hero` dict (`copy_is_block=False`)
- [x] `hero.html` branch-free component; `hero_block.html` simplified to `{% include %}`
- [x] `table_block.html` fixed to use Wagtail's structured context variables
- [x] Semantic color tokens (`bg-light/dark`, `text-light/dark`) applied across all templates
- [x] Block label strings in Title Case throughout
- [x] `components/hero.html` context contract documented in AGENTS.md and PLAN.md
- [x] Agent code review (all blocking issues addressed)
- [x] Human code review + commit

### ✅ Phase 3: Page Types — COMPLETE
- [x] `home/models.py` -- HomePage(BasePage, HeroMixin) with body StreamField
- [x] `pages/models.py` -- ContentPage(BasePage, HeroMixin), IndexPage(BasePage, HeroMixin)
- [x] `forms/models.py` -- FormField(AbstractFormField) + FormPage(BasePage, AbstractEmailForm)
- [x] `templates/base_page.html` -- add `{% block hero %}` between header and content
- [x] Page templates (4 files in `templates/pages/`)
- [x] `templates/components/pagination.html`
- [x] Migrations for `home`, `pages`, `forms`
- [x] `wtrx_tags.page_as_card` template tag for IndexPage child card rendering
- [x] Tests for all 4 page types (home, pages, forms)
- [x] Agent code review
- [x] Human review + commit

Note: page models were later consolidated into `wtrx/` — see Phase 9 below.

### ✅ Phase 4: Navigation & Footer — COMPLETE

- [x] `navigation/header.html` -- logo, nav links, CTA button, mobile hamburger,
  language switcher (`components/language_switcher.html`)
- [x] `navigation/footer.html` -- nav sections, social links, copyright
- [x] `static_src/javascript/components/mobile-menu.js`
- [x] Wire up settings in templates
- [x] `{% trans %}` on all nav/footer UI strings
- [x] `wtrx_tags.py` -- `social_icon` tag + `social_platform_label` filter
- [x] `template` attribute added to all concrete page models
- [x] Fix `{# ... #}` multi-line comment in `hero.html` → `{% comment %}...{% endcomment %}`

### ✅ Phase 5: Frontend Build & Styling — COMPLETE (commit f56c74d)
- [x] `tailwind.config.js` (TW3) with full semantic token system (primary, secondary,
  accent, neutral + error, success, warning status tokens)
- [x] `@tailwindcss/typography` and `@tailwindcss/forms` plugins installed and registered
- [x] `static_src/css/main.css` with Tailwind directives and base layer customizations
  (heading font family, form focus ring)
- [x] JS delivery: `make build-js` copies `static_src/javascript/` to `static_compiled/js/`;
  `make build` and `make build-prod` run JS copy + CSS build; `base.html` loads
  JS via `<script type="module">`
- [x] `static_src/javascript/components/accordion.js` — accordion toggle with
  `data-accordion-toggle` / `data-accordion-content` / `aria-expanded`
- [x] `static_src/javascript/components/form-ajax.js` — AJAX form submission for
  FormPage (`[data-form-page]`) and SignupBlock wagtail_forms variant
  (`[data-signup-block]`); fetches form HTML, handles submit, shows thank-you on success
- [x] `main.js` updated to import and init Accordion + FormAjax components
- [x] Templates updated: `text-red-600` → `text-error-600`; Phase 5 comments removed;
  `signup_wagtail_forms_block.html` restructured with `<noscript>` fallback,
  `[data-form-container]`, and `[data-thank-you]` for form-ajax.js
- [x] `static_compiled/` rebuilt (CSS with typography/forms plugins + JS copied)
- [x] Responsive testing (deferred — templates already use responsive Tailwind utilities)
- [x] Style all block templates with semantic Tailwind utilities (done in Phase 4)
- [x] Style page templates, header, footer, hero (done in Phase 4)

### 🔄 Phase 6: Polish & Setup — IN PROGRESS
- [x] `wtrx/constants.py` -- shared constants (`RICHTEXT_FEATURES_FULL`,
  `RICHTEXT_FEATURES_INLINE`, `RICHTEXT_FEATURES_HERO`, `CHARFIELD_MAX_LENGTH`)
- [x] `wtrx/blocks/__init__.py` -- imports from `constants.py` instead of local defs
- [x] `wtrx/models.py` -- `HeroMixin.hero_copy` uses `RICHTEXT_FEATURES_HERO`
- [x] `pages/models.py`, `forms/models.py` -- use `RICHTEXT_FEATURES_INLINE`
- [x] `wtrx/wagtail_hooks.py` -- block visibility hooks (admin URL endpoint +
  `insert_global_admin_js`) that hide irrelevant block types based on
  IntegrationSettings at request time
- [x] `management/commands/setup_site.py` -- interactive setup command: prompts for
  site name, language, donation platform, signup platform; creates Site, HomePage,
  IntegrationSettings
- [x] `donate_block.html` -- fallback to `IntegrationSettings.donation_suggested_amounts`
  when block-level `override_amounts` is empty
- [x] `IntegrationSettings.donation_suggested_amounts_list` property for template iteration
- [x] Tests for constants, wagtail_hooks, setup_site command, site_settings
- [x] `management/commands/create_test_page.py` -- creates a `ContentPage` with
  every block type and every field permutation populated (ImageBlock, CardBlock,
  PersonCardBlock, CalloutBlock with both alignments, ButtonBlock in all 3 styles,
  QuoteBlock with/without attribution, HeroBlock full/minimal, DonateBlock
  with/without overrides, SectionBlock with all 4 backgrounds and sm/md/lg padding);
  loads a real JPEG from `fixtures/placeholder.jpg` for all image-bearing blocks
- [x] `fixtures/placeholder.jpg` -- committed 1200×800 JPEG placeholder image
  (indigo background, white label text) used by `create_test_page` for visual QA
- [x] `wtrx/tests/test_create_test_page.py` -- automated rendering tests: command
  creates the page, HTTP GET returns 200, each block type and variant produces
  expected output (43 tests total)
- [x] `video_block.html` -- fixed missing `{% load wagtailembeds_tags %}` (caused
  `TemplateSyntaxError: Invalid block tag 'embed'`)
- [x] `video_block.html` -- fixed YouTube iframe size: added Tailwind arbitrary
  variant `[&>iframe]:absolute [&>iframe]:inset-0 [&>iframe]:w-full [&>iframe]:h-full`
  to wrapper so the oEmbed-generated iframe fills the `aspect-video` container
- [x] Social icon display toggles: `SocialSettings.show_in_header` (default False),
  `SocialSettings.show_in_footer` (default True) — social icons rendered in header
  menu panel and/or footer based on these flags
- [x] Footer layout modes: `FooterSettings.layout` choice (columns/minimal) +
  `FooterSettings.minimal_links` StreamField — minimal layout is a single-row bar
  with logo, copyright, social icons, and inline links
- [x] Footer logo: `BrandingSEOSettings.logo` shown at top of columns-layout footer
  and left of minimal-layout footer when set
- [x] Anchor links in nav: `AnchorLinkBlock` added to NavigationSettings.primary_navigation,
  FooterColumnBlock.links, and FooterSettings.minimal_links; renders as `<a href="#anchor">`
- [x] Collapsed desktop menu: `NavigationSettings.collapse_desktop_menu` (BooleanField,
  default False) — when True, desktop nav is hidden and hamburger is shown at all
  breakpoints; uses existing mobile-menu.js (no JS changes needed)
- [x] CTA anchor link: `NavigationSettings.cta_anchor` — CTA button can link to an
  anchor instead of a page or URL
- [x] Transparent header on HomePage: `HomePage.use_transparent_header` (BooleanField,
  default False) — makes header `position:absolute` over hero, transparent bg, light
  text; automatically uses `BrandingSEOSettings.dark_logo` when enabled
- [x] `wtr-*` CSS class hooks on all critical elements: `wtr-header`, `wtr-footer`,
  `wtr-hero`, `wtr-section`, `wtr-card`, `wtr-card-grid`, `wtr-callout`, `wtr-accordion`,
  `wtr-quote`, `wtr-donate`, `wtr-signup`, `wtr-social-links` — no default styles,
  pure theme override hooks
- [x] Block/settings label capitalization normalized to sentence case throughout
  `site_settings.py`
- [x] `SectionContentBlock` — extracted the inline tuple-list `StreamBlock` inside
  `SectionBlock` into a named declarative `StreamBlock` subclass. Fork sites can now
  subclass `SectionContentBlock` and override individual child blocks (e.g. swap
  `CardBlock` for a site-specific subclass) without duplicating the entire 17-entry
  block list. Migration-neutral: Wagtail's `deconstruct()` serializes both forms
  identically as `wagtail.blocks.StreamBlock`.
- [x] `CardBlock.icon` — optional `ImageChooserBlock` displayed beside the card
  heading. Rendered at 24x24px with `alt=""` (decorative). `card.html` template
  updated with conditional icon rendering. `create_test_page` and tests updated.
- [x] README `Customizing Blocks` section — documents the subclass-and-override
  pattern for fork sites, with a concrete example of adding a field to `CardBlock`
- [ ] `fixtures/demo.json` -- demo content (deferred)
- [ ] Verify settings panels work
- [ ] Verify AJAX form submission
- [ ] Verify ActBlue donation link generation
- [x] Verify Action Network widget embedding
- [ ] Verify IndexPage child page listing with pagination
- [ ] Verify i18n: add a second language, translate a page, confirm language switcher works

---

### Phase 7: Tailwind CSS v4 Upgrade — COMPLETE (branch feature/tailwind-4)
- [x] Ran `npx @tailwindcss/upgrade` to migrate TW3 → TW4
- [x] `tailwind.config.js` deleted; all theme config migrated to `@theme {}` block in
  `static_src/css/theme.css` (split from `main.css` for cleaner client fork merges)
- [x] `@tailwind` directives replaced with `@import "tailwindcss"`
- [x] `@plugin` directives added for `@tailwindcss/typography` and `@tailwindcss/forms`
- [x] All color scales and font tokens migrated to CSS custom properties under `@theme {}`
  in `static_src/css/theme.css`; named `[data-theme]` presets (grassroots, solidarity)
  included for future CMS theme switcher
- [x] Compatibility `@layer base` block added for default border color
- [x] Utility renames applied in templates: `shadow-sm`→`shadow-xs`, `rounded`→`rounded-sm`,
  `outline-none`→`outline-hidden`, arbitrary variant syntax updated for TW4
- [x] Added `@tailwindcss/cli: ^4.2.2` to `package.json` devDependencies (separate CLI
  package required in TW4; `tailwindcss` alone no longer provides the binary)
- [x] Reverted all bad changes from the upgrade tool:
  - `'outline'` choice value in `BUTTON_STYLE_CHOICES` (tool confused it with CSS rename)
  - All migration files (tool corrupted frozen `block_lookup` dicts)
  - Docstring in `test_images.py` ("rounded to the nearest integer" mangled)
- [x] `npm run build` succeeds: `≈ tailwindcss v4.2.2 / Done in 132ms`
- [x] 189 Django tests pass
- [x] PLAN.md, AGENTS.md, README.md updated for TW4

### ✅ Phase 9: App Consolidation — COMPLETE (branch feature/consolidate-apps)

Consolidated the four thin Django apps (`home`, `pages`, `forms`, `search`) into `wtrx/`
so the entire reusable platform lives in one self-contained app, making it easier to
rebase forks and eventually extract `wtrx/` to a pip package.

- [x] `wtrx/models.py` -- added `HomePage`, `ContentPage`, `IndexPage`, `FormField`,
  `FormPage`, `ITEMS_PER_PAGE` constant; updated all `parent_page_types`/`subpage_types`
  strings to `"wagtail_wtr_wtrx.*"` (later updated to `"wtrx.*"` in Phase 10)
- [x] `wtrx/views.py` -- new file; `search()` view moved from `search/views.py`
- [x] `wtrx/blocks/__init__.py` -- updated `page_type` reference to `"wagtail_wtr_wtrx.FormPage"`
- [x] `urls.py` -- search view imported from `wtrx` instead of `search`
- [x] `settings/base.py` -- removed `wagtail_wtr.home`, `.pages`, `.forms`, `.search`
  from `INSTALLED_APPS`; only `wagtail_wtr.wtrx` remains (later updated to `wtrx` in Phase 10)
- [x] Management commands updated: deferred `HomePage`/`ContentPage` imports now point to `wtrx.models`
- [x] Test files: `test_pages.py`, `test_forms.py`, `test_search.py` consolidated into
  `wtrx/tests/`; stale imports in `test_create_test_page.py` and `test_setup_site.py` fixed
- [x] Deleted `wagtail_wtr/home/`, `wagtail_wtr/pages/`, `wagtail_wtr/forms/`, `wagtail_wtr/search/`
- [x] Deleted `wagtail_wtr/users/`; removed `AUTH_USER_MODEL` override; Django's built-in
  `auth.User` is now used directly (same approach as CodeRed CMS)
- [x] Migrations reset: deleted old `0001`–`0003`, regenerated fresh `0001_initial.py`
  covering all 12 models (including page models previously split across 3 migration lineages)
- [x] 234 tests pass on fresh DB
- [x] `AGENTS.md` updated: repo structure tree, Architecture Rules 1 and 8
- [x] `README.md` updated: what-to-customize table, don't-edit table
- [x] `PLAN.md` updated: directory tree, Key Design Decisions table, Phase 3 note, this entry
- [x] Agent code review
- [x] Human review + commit

### ✅ Phase 10: Move wtrx/ to Repo Root — COMPLETE

Moved `wagtail_wtr/wtrx/` to `wtrx/` at the repo root (sibling to `wagtail_wtr/`),
matching the CodeRed CMS pattern where the reusable app is a top-level package
separate from the project config package.

- [x] `git mv wagtail_wtr/wtrx wtrx` — move the directory
- [x] `wtrx/apps.py` -- `name = "wtrx"`, `label = "wtrx"` (was `wagtail_wtr.wtrx` / `wagtail_wtr_wtrx`)
- [x] `wagtail_wtr/settings/base.py` -- `INSTALLED_APPS`: `"wtrx"` (was `"wagtail_wtr.wtrx"`)
- [x] `wagtail_wtr/settings/base.py` -- `WAGTAILIMAGES_IMAGE_MODEL`: `"wtrx.CustomImage"`
- [x] `wagtail_wtr/urls.py` -- import from `wtrx` (was `wagtail_wtr.wtrx`)
- [x] `wtrx/blocks/__init__.py` -- absolute import from `wtrx.constants`
- [x] `wtrx/blocks/__init__.py` -- `page_type="wtrx.FormPage"` (was `"wagtail_wtr_wtrx.FormPage"`)
- [x] `wtrx/wagtail_hooks.py` -- deferred import from `wtrx.site_settings`
- [x] `wtrx/templatetags/wtrx_tags.py` -- import from `wtrx.site_settings`
- [x] `wtrx/management/commands/setup_site.py` -- deferred imports from `wtrx.models` / `wtrx.site_settings`
- [x] `wtrx/management/commands/create_test_page.py` -- deferred imports from `wtrx.images` / `wtrx.models`
- [x] `wtrx/models.py` -- all `parent_page_types`/`subpage_types` strings updated to `"wtrx.*"`
- [x] Templates (5 files) -- `settings.wagtail_wtr_wtrx.X` → `settings.wtrx.X`
- [x] Test files (10 files) -- imports updated from `wagtail_wtr.wtrx.*` → `wtrx.*`
- [x] Migrations reset: deleted `0001_initial.py`, regenerated fresh `0001_initial.py`
- [x] `Makefile` -- `test` target: `python manage.py test wtrx wagtail_wtr`
- [x] `AGENTS.md`, `README.md`, `PLAN.md` updated
- [x] 235 tests pass

### ✅ Phase 11: CDN Cache Invalidation — COMPLETE

Provider-agnostic cache invalidation built into `wtrx/`. Designed around the
"support but don't depend on" principle — everything works normally when no CDN
is configured.

- [x] `wagtail.contrib.frontend_cache` added to `INSTALLED_APPS` in `base.py`
  (handles per-URL purge on page publish/unpublish automatically)
- [x] `production.py` — conditional `WAGTAILFRONTENDCACHE` block: if
  `CLOUDFLARE_BEARER_TOKEN` and `CLOUDFLARE_ZONE_ID` env vars are both present,
  configures the Cloudflare backend; otherwise leaves `WAGTAILFRONTENDCACHE` unset
  (no-op for all cache code)
- [x] `wtrx/cache.py` — provider-agnostic `purge_all()` and `purge_page_with_related()`:
  - `PURGE_ALL_HANDLERS` dict maps backend class paths to handler functions (adding a
    new CDN = add one entry)
  - `_purge_all_cloudflare()` calls `POST /zones/{zone_id}/purge_cache` with
    `{"purge_everything": true}`; supports both Bearer-token and legacy Email+API-key auth
  - `_purge_all_fallback()` purges all live page URLs via `PurgeBatch` for backends
    that have no single-call purge-all API
  - `purge_all()` reads `WAGTAILFRONTENDCACHE`, dispatches per backend, silent no-op
    when unconfigured
  - `purge_page_with_related(page)` purges a page and its parent if the parent is an
    `IndexPage`; silent no-op when unconfigured
- [x] `wtrx/signals.py` — signal handlers and `connect_signals()`:
  - `on_settings_saved` connected to `post_save` for all 5 settings models
    (`BrandingSEOSettings`, `NavigationSettings`, `FooterSettings`, `SocialSettings`,
    `IntegrationSettings`); calls `purge_all()` because header/footer affects every page
  - `on_page_published` connected to Wagtail's `page_published` signal; calls
    `purge_page_with_related()` to also refresh parent index listings
  - Signal connection deferred inside `connect_signals()` to avoid
    `AppRegistryNotReady` errors
- [x] `wtrx/apps.py` — `WtrxConfig.ready()` calls `connect_signals()` from
  `wtrx.signals`
- [x] `wtrx/tests/test_cache.py` — 21 tests:
  - `purge_all()` no-ops silently when not configured
  - Cloudflare API called with correct payload + auth when configured
  - Bearer-token and legacy Email+API-key auth paths tested
  - Graceful handling of missing ZONEID, missing credentials, HTTP errors, network exceptions
  - Registry dispatch routes correctly to CF handler and fallback handler
  - `on_settings_saved` fires `purge_all` for each of the 5 settings models
  - `purge_page_with_related` purges parent IndexPage when applicable
  - `purge_page_with_related` is a no-op when not configured
  - Does not raise when page has no parent
- [x] `README.md` — Cloudflare configuration section under Deployment: zone ID
  location, how to create an API token, how the two purge modes work, rate limits,
  silent no-op behavior
- [x] `AGENTS.md` — pitfall added for `WAGTAILFRONTENDCACHE` env vars and
  `cached_property` vs method call (`.specific` not `.specific()`)
- [x] 256 tests pass

---

### Phase 12: Hosting Strategy — NOT STARTED

Plan and implement a pluggable hosting adapter pattern to support deploying
wagtail-wtr sites on multiple cloud platforms.

- [ ] Evaluate Render, Railway, and AWS Lightsail as primary targets
- [ ] Design pluggable host adapters: per-host `production_<host>.py` settings
  overlay or env-var-driven selection
- [ ] S3 (or compatible) media storage: `django-storages[s3]` + `wagtail-storages`
  are already in `pyproject.toml`; document bucket naming, CORS, and IAM policy
- [ ] Platform-specific `Procfile` / `render.yaml` / `railway.json` starter files
- [ ] `make deploy-<host>` convenience targets in `Makefile`

### Phase 13: ADR Documentation — NOT STARTED

Create an Architecture Decision Record (ADR) log documenting the key decisions
made in the platform. This helps onboard new developers and provides rationale
for future maintainers.

- [ ] Choose ADR format (Nygard-style `docs/adr/NNNN-title.md` is conventional)
- [ ] Document the upstream/fork strategy (why fork over subpackage)
- [ ] Document the `wtrx/` extraction roadmap (CodeRed CMS pattern)
- [ ] Document the Tailwind v4 token system and why no `tailwind.config.js`
- [ ] Document the "no custom User model" decision
- [ ] Document the "no DB access at import time" constraint and how it's enforced

### Phase 14: SMTP & Provisioning Automation — NOT STARTED

Automate new-site provisioning to reduce the time from fork to running production site.

- [ ] SMTP: document Mailgun, AWS SES, and Postmark options; add
  `EMAIL_BACKEND` / `EMAIL_HOST` env-var-driven config to `production.py`
- [ ] Provisioning script: `make provision` that creates S3 bucket, IAM policy,
  SES domain identity, and Cloudflare DNS entries for a new fork
- [ ] `make env-template` that outputs a `.env.example` with all required and
  optional production env vars and their descriptions

---

The goal is to catch regressions in block rendering automatically — both at the
HTML level (existing) and at the pixel level (visual regression).

#### 7a: Keep the test page in sync with blocks

- `create_test_page.py` is the single source of truth for test content. Every
  time a block is added, removed, or has fields changed, the command must be
  updated to include realistic sample data for that block.
- `make test-page` always runs with `--force` so it reflects the latest block
  definitions.
- Convention: when a new block is added to `BodyStreamBlock`, a corresponding
  `_<block_name>_block()` factory function must be added to `create_test_page.py`
  and the block appended to `_FLAT_BLOCKS`. A test in `test_create_test_page.py`
  must assert that the block's key content string appears in the rendered response.
- CI gate: `make test` already covers `test_create_test_page.py`. This ensures
  the test page renders without errors on every push.

#### 7b: Visual regression testing with Playwright

Planned tooling: **Playwright** (`playwright` Python package) with
**pytest-playwright**.

Workflow:
1. `make visual-baseline` — start dev server, run `create_test_page --force`,
   capture full-page screenshots of `/test-blocks/` at three viewports
   (mobile 390 px, tablet 768 px, desktop 1280 px). Store PNGs in
   `tests/visual/baselines/`.
2. `make visual-test` — same capture, then pixel-diff each screenshot against
   the stored baseline using Playwright's `expect(page).to_have_screenshot()`.
   Fail if any diff exceeds a configurable threshold (e.g., 0.1 % of pixels).
3. `make visual-update` — overwrite baselines after an intentional design change.

Key decisions to make when implementing:
- **Baseline storage**: commit baseline PNGs to the repo (small, deterministic)
  or store them in CI artifacts only. Committing is simpler for a small project.
- **Font rendering**: use a fixed font stack in the test environment or disable
  web fonts to avoid cross-platform pixel drift.
- **Flaky areas**: mask dynamic content (timestamps, Action Network widget,
  YouTube embeds) using Playwright's `mask` option.
- **CI integration**: run `visual-test` on pull requests; fail the PR if diffs
  exceed threshold. The `visual-update` target is only run manually.

Implementation steps (when ready):
- [ ] Add `playwright`, `pytest-playwright` to `[dev]` extras in `pyproject.toml`
- [ ] `playwright install chromium` (add to `make venv` or a separate `make playwright-install`)
- [ ] `tests/visual/conftest.py` -- shared fixtures (base URL, viewport sizes, page setup)
- [ ] `tests/visual/test_block_test_page.py` -- screenshot + diff tests per viewport
- [ ] `tests/visual/baselines/` -- initial baseline PNGs (generated by `make visual-baseline`)
- [ ] `Makefile` targets: `visual-baseline`, `visual-test`, `visual-update`
- [ ] CI step (GitHub Actions): run `make visual-test` after `make test`

---

### Phase 15: CI, Automated Testing & Linting — NOT STARTED

Ensure contributors (and forks) cannot silently break conventions, upstream
compatibility, or code quality. The goal is a green-CI gate on every PR.

#### 15a: GitHub Actions workflow

- [ ] `.github/workflows/ci.yml` — triggered on `push` and `pull_request` to
  `main`. Jobs:
  - **lint** — `ruff check .` + `ruff format --check .` (or `flake8` + `black`)
  - **test** — `python manage.py test wtrx wagtail_wtr` against a matrix of
    supported Python versions (3.11, 3.12)
  - **migrations check** — `python manage.py migrate --check` + `python manage.py
    makemigrations --check --dry-run` to catch missing or unapplied migrations
  - **build** — `make build-prod` to verify CSS/JS compiles cleanly
- [ ] Add `pyproject.toml` config for `ruff` (line-length 119, import ordering
  matching AGENTS.md conventions, Django/Wagtail-aware rules)
- [ ] Add `pyproject.toml` config for `mypy` or skip for now (models/blocks don't
  require type hints per AGENTS.md; revisit when extracting `wtrx/` as a package)

#### 15b: Pre-commit hooks

- [ ] `.pre-commit-config.yaml` with:
  - `ruff` (lint + format)
  - `check-merge-conflict`, `end-of-file-fixer`, `trailing-whitespace`
  - `python manage.py makemigrations --check` (fail if model changes have no migration)
- [ ] Document `pre-commit install` in `README.md` and `Makefile` (`make install-hooks`)

#### 15c: Fork compatibility test

A lightweight smoke test to verify that a fork that subclasses `wtrx/` models
does not break silently when upstream changes are merged.

- [ ] `wtrx/tests/test_fork_compat.py` — asserts that all concrete page models
  have a `template` attribute, all `BodyStreamBlock` children have `icon` and
  `template` in their `Meta`, and all settings models are registered with
  `@register_setting`
- [ ] Run as part of the normal `make test` suite (no separate step needed)

#### 15d: Linting conventions enforcement

- [ ] Add `ruff` rules to enforce AGENTS.md conventions automatically:
  - `I` (isort) — import ordering (stdlib → django → wagtail → third-party → local)
  - `UP` (pyupgrade) — modern Python syntax
  - `DJ` (flake8-django) — Django-specific gotchas
  - `TID252` — ban relative imports from `wtrx/` (enforce `from wtrx.x import y`)
- [ ] `make lint` target in `Makefile` that runs `ruff check . && ruff format --check .`
- [ ] `make lint-fix` target that runs `ruff check --fix . && ruff format .`

---

## Future (Documented, Not Built)

- **Donation platforms**: Action Network, Action Kit, PayPal, Stripe
- **Signup platforms**: Action Kit
- **Inline Action Network forms via API** (currently uses their JS widget)
- **Dark mode**
- **Multi-site / multi-tenancy**
- **pip extraction of wtrx/ package** (`wagtail-wtrx` on PyPI, following CodeRed CMS pattern)
- **Theme switching** (multiple built-in themes)
- **Additional blocks**: Stats, Events, Logo showcase, Countdown, Social links block
- **Additional pages**: Blog/news listing, event listing

---

## Reference Repos

These were analyzed during planning:

- **[wagtail/bakerydemo](https://github.com/wagtail/bakerydemo)** -- Official Wagtail
  patterns: multi-app structure, split settings, Docker, snippets.
- **[coderedcorp/coderedcms](https://github.com/coderedcorp/coderedcms)** -- Primary
  reference for the eventual `wagtail-wtrx` pip extraction pattern. Concrete base
  page models, project template embedded in package, CodeRed CMS architecture.
- **[torchbox/torchbox.com](https://github.com/torchbox/torchbox.com)** -- Production
   Wagtail site with Tailwind, poetry, Docker.
- **websites-for-all** (With the Ranks' previous project, cloned in `websites-for-all/`
  for reference) -- Carried forward feature set, redesigned architecture.

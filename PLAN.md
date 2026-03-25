# wagtail-wtr: Implementation Plan

## Overview

A Wagtail project template for campaign, nonprofit, and organizer websites. Used via
`wagtail start --template`. Contains a reusable `wtrx/` sub-app designed for eventual
extraction to a pip package.

**Target users (MVP)**: Developers at With the Ranks who spin up new campaign/nonprofit
sites. They want to get 80% done fast, then theme and add site-specific functionality.

---

## Architecture

The **entire repo root IS the template** (following the news-template pattern).
`project_name/` is renamed by `wagtail start`. `wtrx/` is the core reusable app —
client sites don't edit it, they extend/override.

```
wagtail-wtr/
├── project_name/
│   ├── wtrx/                       # Core reusable app (DON'T EDIT on client sites)
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── blocks/
│   │   │   ├── __init__.py         # Exports BodyStreamBlock
│   │   │   ├── content.py          # TextBlock, ImageBlock, VideoBlock, ButtonBlock,
│   │   │   │                       #   QuoteBlock, RawHTMLBlock, TableBlock
│   │   │   ├── layout.py           # SectionBlock, CardGridBlock, AccordionBlock
│   │   │   ├── composite.py        # CalloutBlock, HeroBlock
│   │   │   ├── cards.py            # CardBlock, PersonCardBlock
│   │   │   └── actions.py          # DonateBlock, SignupBlock variants
│   │   ├── models.py               # BasePage, HeroMixin
│   │   ├── site_settings.py        # BrandingSEOSettings, NavigationSettings,
│   │   │                           #   FooterSettings, SocialSettings, IntegrationSettings
│   │   ├── images.py               # CustomImage, Rendition
│   │   ├── templatetags/
│   │   │   ├── __init__.py
│   │   │   └── wtrx_tags.py
│   │   ├── wagtail_hooks.py
│   │   └── management/
│   │       └── commands/
│   │           └── setup_site.py   # Interactive setup command
│   ├── home/                       # HomePage model
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── migrations/
│   ├── pages/                      # ContentPage, IndexPage models
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── migrations/
│   ├── forms/                      # FormPage model
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── migrations/
│   ├── users/                      # Custom user model
│   │   ├── __init__.py
│   │   ├── apps.py
│   │   ├── models.py
│   │   └── migrations/
│   ├── search/                     # Search view
│   │   ├── __init__.py
│   │   └── views.py
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
│   │       └── form-ajax.js        # AJAX form submission for FormPage/SignupBlock
│   └── css/
│       └── main.css                # Tailwind directives + component styles
├── static_compiled/                # Tailwind CLI output (committed)
├── fixtures/
│   └── demo.json
├── tailwind.config.js
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
| Template mechanism | Repo root IS the template | Matches Wagtail news-template pattern |
| Reusable app | `wtrx/` sub-app inside `project_name/` | Visible boundary prevents mixing core + site-specific code. Designed for eventual pip extraction. |
| CSS framework | Tailwind with semantic design tokens | `bg-primary`, `font-heading`, etc. Sites customize via `tailwind.config.js`. No raw color values in templates. |
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
| heading | CharBlock | **Yes** |
| description | TextBlock (plain) | No |
| image | ImageChooserBlock | No |
| link_page | PageChooserBlock | No |
| link_url | URLBlock | No |

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
| action_network_id | CharBlock | **Yes** |

Renders Action Network's JS widget.

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
- **Fields**: body (BodyStreamBlock)
- **Template**: `pages/home_page.html`
- **Parent**: Root (Site root page)
- **Notes**: Hero at top (from HeroMixin), StreamField body below

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

---

## Core Models & Mixins

### BasePage (abstract)

`BasePage` must include `TranslatableMixin` for wagtail-localize:

```python
class BasePage(TranslatableMixin, Page):
    ...
```

| Field | Type | Notes |
|---|---|---|
| meta_image | ForeignKey to CustomImage | On promote_panels. Fallback to BrandingSEOSettings.default_meta_image |
| hide_from_search | BooleanField | Toggle visibility in search results (used in `BasePage.get_sitemap_urls()`) |

### HeroMixin (abstract)

| Field | Type | Notes |
|---|---|---|
| hero_headline | CharField | Optional. Overrides page title as displayed h1. |
| hero_copy | RichTextField | Optional. Subtext below headline. |
| hero_image | ForeignKey to CustomImage | Optional. Hero background/feature image. |
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
| primary_navigation | StreamField (InternalLinkBlock, ExternalLinkBlock) | No |
| cta_text | CharField | No |
| cta_page | ForeignKey to Page | No |
| cta_url | URLField | No |

### Settings > Footer (`FooterSettings`)

| Field | Type | Required |
|---|---|---|
| footer_navigation | StreamField (FooterSectionBlock: heading + ListBlock of links) | No |
| copyright_text | CharField | No, falls back to "(c) {year} {site name}" |

### Settings > Social (`SocialSettings`)

| Field | Type | Required |
|---|---|---|
| social_links | StreamField of SocialLinkBlock (platform: ChoiceBlock, url: URLBlock) | No |

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
- Logo left (from BrandingSEOSettings.logo)
- Nav links right (from NavigationSettings.primary_navigation)
- CTA button right (from NavigationSettings.cta_text/cta_page/cta_url)
- Mobile: logo left, CTA button, hamburger right. Hamburger opens nav overlay.

### Footer (`navigation/footer.html`)
- Footer nav sections (from FooterSettings.footer_navigation)
- Social links (from SocialSettings.social_links)
- Copyright line (from FooterSettings.copyright_text, fallback: "(c) {year} {site name}")

### Hero (`components/hero.html`)
- h1: `hero_headline` if set, otherwise `page.title`
- Subtext: `hero_copy`
- Image: `hero_image`
- CTA button: `hero_link_text` + `hero_link_page`/`hero_link_url`
- Same template used by all page types

HTML templates use standard Django template syntax wrapped in
`{% verbatim %}{% endverbatim %}` (required for `wagtail start --template`
compatibility — see AGENTS.md for the full explanation). Only `.py` files
contain `{{ project_name }}` substitution.

---

## Frontend Build

### Stack
- **Tailwind CSS 3.4** via Tailwind CLI
- **Vanilla JS** served directly (no bundler)

### `tailwind.config.js` -- Semantic Design Tokens

```javascript
module.exports = {
  content: ['./templates/**/*.html', './static_src/**/*.{js,ts}'],
  theme: {
    extend: {
      colors: {
        primary: { /* scale 50-950 */ },
        secondary: { /* scale */ },
        accent: { /* scale */ },
        neutral: { /* scale */ },
      },
      fontFamily: {
        heading: [/* heading font */],
        body: [/* body font */],
      },
    },
  },
};
```

Sites customize by editing `tailwind.config.js` -- change `primary` from blue to green,
change `font-heading`, etc.

### npm scripts

```json
{
  "build": "tailwindcss -i ./static_src/css/main.css -o ./static_compiled/css/main.css",
  "build:prod": "tailwindcss -i ./static_src/css/main.css -o ./static_compiled/css/main.css --minify",
  "start": "tailwindcss -i ./static_src/css/main.css -o ./static_compiled/css/main.css --watch"
}
```

### Output
`static_src/css/main.css` -> Tailwind CLI -> `static_compiled/css/main.css` (committed to repo)
`static_src/javascript/` -> served directly (no bundling)

---

## Python Dependencies (pyproject.toml)

```
django>=5.1,<5.3
wagtail>=6.4,<6.5
wagtail-localize
wagtailmedia
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
tailwindcss
```

---

## Management Commands

### `setup_site`

Interactive command run after `wagtail start`:

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

### Phase 0: Project Scaffolding
- Create directory structure
- `manage.py` with `{{ project_name }}` substitution
- `settings/` (base.py, dev.py, production.py) following news-template patterns,
  including i18n settings (`USE_I18N`, `WAGTAIL_I18N_ENABLED`, `LANGUAGES`)
- `urls.py` with `i18n_patterns()` wrapper, `wsgi.py`
- `pyproject.toml` (including `wagtail-localize`)
- `package.json`, `tailwind.config.js` with semantic tokens
- `Dockerfile`, `Makefile`, `.gitignore`, `.dockerignore`, `.nvmrc`
- `wtrx/` app skeleton (`apps.py`, `__init__.py`)
- `users/` app with custom user model
- `search/` app with search view
- Base templates (`base.html`, `base_page.html`, `404.html`, `500.html`)
  with `{% load i18n %}` and `{% trans %}` on all UI strings,
  all wrapped in `{% verbatim %}{% endverbatim %}`
- Verify `wagtail start --template` works with the bare skeleton

### Phase 1: Core Models & Settings
- `wtrx/images.py` -- CustomImage model
- `wtrx/models.py` -- BasePage, HeroMixin
- `wtrx/site_settings.py` -- all 5 settings panels
- Navigation link blocks (InternalLinkBlock, ExternalLinkBlock) for settings
- Template tags for accessing settings in templates
- Migrations

### Phase 2: StreamField Blocks
- `wtrx/blocks/content.py` -- 7 content blocks (use `gettext_lazy` for default values)
- `wtrx/blocks/layout.py` -- 3 layout blocks
- `wtrx/blocks/composite.py` -- CalloutBlock, HeroBlock
- `wtrx/blocks/cards.py` -- CardBlock, PersonCardBlock
- `wtrx/blocks/actions.py` -- DonateBlock, SignupBlock variants, dynamic registration
- `wtrx/blocks/__init__.py` -- BodyStreamBlock assembly
- Block templates (16 files, all with `{% load i18n %}` and `{% trans %}` on UI strings)
- Component templates (hero, button, card, person_card, pagination)

### Phase 3: Page Types
- `home/models.py` -- HomePage
- `pages/models.py` -- ContentPage, IndexPage
- `forms/models.py` -- FormPage
- Page templates (4 files)
- Migrations

### Phase 4: Navigation & Footer
- `navigation/header.html` -- logo, nav links, CTA button, mobile hamburger,
  language switcher (`components/language_switcher.html`)
- `navigation/footer.html` -- nav sections, social links, copyright
- `static_src/javascript/components/mobile-menu.js`
- Wire up settings in templates
- `{% trans %}` on all nav/footer UI strings

### Phase 5: Frontend Build & Styling
- Tailwind config with full semantic token system
- `static_src/css/main.css` with Tailwind directives
- Style all block templates with semantic Tailwind utilities
- Style page templates, header, footer, hero
- `static_src/javascript/components/form-ajax.js` for AJAX form submission
- Build and commit `static_compiled/`
- Responsive testing

### Phase 6: Polish & Setup
- `wtrx/wagtail_hooks.py` -- custom rich text features
- `management/commands/setup_site.py` -- interactive setup command including
  language configuration prompt
- `fixtures/demo.json` -- demo content
- Verify `wagtail start --template` works end-to-end
- Verify all blocks render correctly
- Verify settings panels work
- Verify AJAX form submission
- Verify ActBlue donation link generation
- Verify Action Network widget embedding
- Verify IndexPage child page listing with pagination
- Verify i18n: add a second language, translate a page, confirm language switcher works

---

## Future (Documented, Not Built)

- **Donation platforms**: Action Network, Action Kit, PayPal, Stripe
- **Signup platforms**: Action Kit
- **Inline Action Network forms via API** (currently uses their JS widget)
- **Dark mode**
- **Multi-site / multi-tenancy**
- **pip extraction of wtrx/ package** (`wagtail-wtrx` on PyPI)
- **Theme switching** (multiple built-in themes)
- **Additional blocks**: Stats, Events, Logo showcase, Countdown, Social links block
- **Additional pages**: Blog/news listing, event listing

---

## Reference Repos

These were analyzed during planning:

- **[wagtail/news-template](https://github.com/wagtail/news-template)** -- Wagtail's
  default starting template. Primary structural reference for this project.
- **[wagtail/bakerydemo](https://github.com/wagtail/bakerydemo)** -- Official Wagtail
  patterns: multi-app structure, split settings, Docker, snippets.
- **[coderedcorp/coderedcms](https://github.com/coderedcorp/coderedcms)** -- Reusable
  blocks library, Bootstrap 5 layout blocks, snippets, project_template pattern.
- **[torchbox/torchbox.com](https://github.com/torchbox/torchbox.com)** -- Production
   Wagtail site with Tailwind, poetry, Docker.
- **websites-for-all** (With the Ranks' previous project, cloned in `websites-for-all/`
  for reference) -- Carried forward feature set, redesigned architecture.

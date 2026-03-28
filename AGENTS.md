# AGENTS.md -- wagtail-wtr

Guidelines for AI coding agents working in this repository.

## Project Overview

wagtail-wtr is the Wagtail CMS platform used at With the Ranks for campaign,
nonprofit, and organizer websites. It is a working Django/Wagtail project —
not a `wagtail start --template`. New client sites fork or clone this repo.

The core reusable app lives at `wtrx/` (repo root, sibling to `wagtail_wtr/`) and
is designed for eventual extraction to a standalone pip package (`wagtail-wtrx`),
following a pattern similar to CodeRed CMS.

See `PLAN.md` for the full specification and architectural decisions.

## Repository Structure

```
wagtail-wtr/
├── wtrx/                   # Core reusable app (future pip package)
│   ├── blocks/             # StreamField blocks, one file per category
│   ├── migrations/
│   ├── templatetags/
│   ├── templates/wtrx/     # All upstream templates live here (APP_DIRS)
│   ├── tests/
│   ├── apps.py
│   ├── images.py           # CustomImage, CustomRendition
│   ├── models.py           # BasePage, HeroMixin, HomePage, ContentPage, IndexPage, FormField, FormPage
│   ├── views.py            # search() view
│   └── site_settings.py
├── wagtail_wtr/            # Django project package (settings, urls, wsgi only)
│   ├── settings/
│   │   ├── base.py
│   │   ├── dev.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
├── templates/              # Fork override templates (empty in upstream; forks shadow wtrx/ templates here)
├── static_src/             # Frontend source (Tailwind, JS)
├── static_compiled/        # Tailwind CLI output (committed to repo)
├── fixtures/
├── manage.py
├── pyproject.toml
├── Makefile
└── Dockerfile
```

- `wtrx/` -- Core reusable app. All page models live here.
- `wtrx/blocks/` -- StreamField blocks, one file per category.
- `wtrx/site_settings.py` -- All Wagtail site settings models.
- `wtrx/models.py` -- BasePage, HeroMixin, HomePage, ContentPage, IndexPage, FormField, FormPage.
- `wtrx/views.py` -- search() view.
- `wtrx/images.py` -- CustomImage model.
- `templates/` -- Fork override templates (empty in upstream). Forks place shadow templates here to override `wtrx/` defaults. Django's `DIRS` resolver checks this directory first.
- `static_src/` -- Frontend source (Tailwind, JS).
- `static_compiled/` -- Tailwind CLI output (committed to repo).

## How to Dev and Test This Repo

This is a standard Django project. All commands run from the repo root.

### Python (Django)

```bash
make venv                    # Create .venv and install all dependencies
source .venv/bin/activate
make migrate                 # Run migrations
make test                    # Run all tests
make dev                     # Dev server at localhost:8000
make createsuperuser         # Create admin user
make setup                   # Interactive initial setup
```

Granular test runs:

```bash
python manage.py test wtrx wagtail_wtr                               # all tests
python manage.py test wtrx                                           # wtrx app only
python manage.py test wtrx.tests.test_images                        # single module
python manage.py test wtrx.tests.test_images.TestObjectPositionStyle # single class
```

### Generating Migrations

Migrations are generated directly in the repo:

```bash
source .venv/bin/activate
python manage.py makemigrations
python manage.py migrate
python manage.py test wtrx wagtail_wtr
```

Never hand-write migrations. Always use `makemigrations`.

### Frontend (CSS/JS)

```bash
npm install                  # Install Node dependencies (once only)
make build                   # Dev build (CSS via Tailwind CLI + JS copy)
make build-prod              # Production build (CSS minified + JS copy)
make build-js                # Copy JS source to static_compiled/js/
make watch                   # Watch mode (rebuilds CSS on change)
```

`static_compiled/` is committed to the repo so forked client sites have working
CSS and JS immediately without needing to run `npm install` and `make build`.

JavaScript source lives in `static_src/javascript/` and is copied verbatim to
`static_compiled/js/` during `make build`. JS uses ES module syntax and is loaded
via `<script type="module">` in `base.html`. No bundler is needed.

### Docker

```bash
docker build -t wagtail-wtr .   # Build image
make load-data                  # migrate + loaddata fixtures/demo.json + collectstatic
```

## Code Style

### Python

- **Formatter**: Follow PEP 8. Use 4-space indentation. Max line length 119 characters.
- **Imports**: Group in this order, separated by blank lines:
  1. Standard library
  2. Django
  3. Wagtail
  4. Third-party packages
  5. Local app imports
  Use absolute imports with `wtrx` prefix for cross-app imports
  (e.g., `from wtrx.blocks import BodyStreamBlock`).
- **Strings**: Use double quotes for human-readable strings (help_text, verbose_name).
  Use single quotes for identifiers and keys (dict keys, field names, choice values).
- **Models**: One model per logical concern. Use abstract models for shared behavior.
  Always set `related_name='+'` on ForeignKeys that don't need reverse relations.
  Use `on_delete=models.SET_NULL` for optional image/page ForeignKeys.
- **Blocks**: Each block class must have a docstring and a `class Meta` with `icon`
  and `template` pointing to `wtrx/components/streamfield/blocks/<name>.html`
  (relative to the Django templates root — do not include a `templates/` prefix).
  Organize blocks by category in separate files under `wtrx/blocks/`.
- **Constants**: Define field length constants (e.g., `CHARFIELD_MAX_LENGTH = 255`)
  and richtext feature lists at the module level. Never hardcode magic numbers.
- **Naming**: Models use PascalCase. Fields use snake_case. Block classes end in
  `Block`. Settings models end in `Settings`. Abstract mixins end in `Mixin`.
- **Translations**: Use `gettext_lazy` (imported as `_`) for all translatable
  strings in Python code — block default values, field help_text, verbose_name,
  choices labels. Example: `button_text = blocks.CharBlock(default=_("Donate"))`.
- **Type hints**: Not required for Django/Wagtail models and blocks. Use them
  for utility functions and non-Django code.

### Templates (HTML)

- **Standard Django templates**: No special wrappers needed. Write normal templates.
- **Internationalization**: All user-facing UI strings in templates MUST use
  `{% trans "string" %}` (or `{% blocktrans %}...{% endblocktrans %}` for
  multi-word strings with variables). Add `{% load i18n %}` at the top of any
  template that contains translatable strings. This includes button defaults
  ("Donate", "Sign Up", "Read more"), pagination labels, error messages,
  copyright fallback text, and form feedback messages. Block content entered
  by editors is translated via wagtail-localize — only hardcoded UI strings
  need `{% trans %}`.
- **Tailwind**: Use semantic design tokens only. Never use raw color values.
  - Correct: `bg-primary-600`, `font-heading`, `text-neutral-800`, `text-error-600`
  - Wrong: `bg-blue-600`, `font-serif`, `text-gray-800`, `text-red-600`
  - **Status colors**: Use `error-*`, `success-*`, `warning-*` tokens for
    validation messages, alerts, and feedback — never raw red/green/yellow.
- **`wtr-*` CSS class hooks**: Every major layout region and block must have a
  semantic `wtr-<name>` class on its outermost element. These carry no styles —
  they exist solely as stable hooks for client theme overrides. Convention:
  - `wtr-header`, `wtr-footer` — top-level layout regions
  - `wtr-hero` — hero component (both `HeroMixin` pages and `HeroBlock`)
  - `wtr-section`, `wtr-card`, `wtr-card-grid`, `wtr-callout`, `wtr-accordion`, `wtr-quote` — layout blocks
  - `wtr-donate`, `wtr-signup` — conversion blocks
  - `wtr-social-links` — social icons container (in header menu panel and footer)
  Always add the `wtr-*` class in addition to any Tailwind utility classes — never
  replace utilities with it.
- **Components**: Reusable UI lives in `wtrx/templates/wtrx/components/`. Block templates
  live in `wtrx/templates/wtrx/components/streamfield/blocks/`.
  Fork override templates live in `templates/` (project root, checked first by Django's DIRS resolver).
- **Indentation**: 4 spaces for HTML. Use Wagtail template tags
  (`wagtailcore_tags`, `wagtailimages_tags`, etc.) as needed.

### JavaScript

- Vanilla JS only (no frameworks). Class-based components with selector-based init.
- ES module syntax. 4-space indentation. Semicolons required.

### CSS

- Entry point: `static_src/css/main.css`.
- Uses Tailwind CSS v4: `@import 'tailwindcss'` at the top (no `@tailwind` directives).
- Built with `@tailwindcss/cli` (`make build` / `make build-prod` / `make watch`).
- Output goes to `static_compiled/css/main.css` (committed to repo).
- Plugins: `@plugin '@tailwindcss/typography'` and `@plugin '@tailwindcss/forms'`
  declared in `main.css` (no `tailwind.config.js` — that file does not exist in TW4).
- Theme customisation: edit `static_src/css/theme.css`.
  All semantic color scales (`--color-primary-*`, `--color-error-*`, etc.) and
  font stacks (`--font-heading`, `--font-body`) live in the `@theme {}` block there.
  `main.css` imports `theme.css` first, then `tailwindcss`, so tokens are available
  when Tailwind processes utilities. Named theme presets (`[data-theme="grassroots"]`,
  etc.) also live in `theme.css`.
- Minimize custom CSS. Prefer Tailwind utilities in templates.
- If component classes are needed, use the `@utility` directive (TW4 replaces
  `@layer components {}` / `@layer utilities {}` with `@utility`).
- **Never create `tailwind.config.js`**: TW4 does not use it. All config is in CSS.

## Architecture Rules

1. **wtrx/ is self-contained**: All page models (`HomePage`, `ContentPage`, `IndexPage`,
   `FormField`, `FormPage`) and the `search()` view live inside `wtrx/`. `wtrx/` is the
   only project app — no separate `users/` app. Django's built-in `auth.User` is used
   directly; no `AUTH_USER_MODEL` override. No code outside `wtrx/` should exist in the
   project unless a fork needs site-specific customisation.
2. **No custom user model**: Use `django.contrib.auth.models.User` directly. Forks that
   need custom user fields should add their own app with a `AbstractUser` subclass and
   set `AUTH_USER_MODEL` in their fork's settings — not in upstream.
3. **Settings over hardcoding**: Platform-specific behavior (ActBlue, Action Network)
   is driven by `IntegrationSettings`, not hardcoded in blocks or templates.
4. **Block visibility via hooks, not import-time DB reads**: All SignupBlock
   variants are always registered in `BodyStreamBlock`. Irrelevant variants are
   hidden in the Wagtail editor via `wagtail_hooks.py`, which reads
   `IntegrationSettings` at request time. Never read the database at
   class-definition or import time — Django's ORM is not available then.
5. **No raw columns/grids in blocks**: Layout control is through opinionated
   composite blocks (SectionBlock, CardGridBlock, CalloutBlock). Editors should
   not be able to create arbitrary column layouts.
6. **i18n from day one**: Every hardcoded UI string is translatable from the
   start. Use `{% trans %}` in templates and `gettext_lazy` in Python. Never
   add raw English strings directly to templates or block defaults without
   wrapping them. Editor-entered content is handled by wagtail-localize.
7. **HeroMixin vs HeroBlock**: `HeroMixin` is an abstract Django model mixin
   added to page classes (HomePage, ContentPage, etc.) that provides a
   dedicated hero section at the top of the page. `HeroBlock` is a StreamField
   block for placing a hero-style section *within* the body StreamField (mid-page).
   They use the same component template (`components/hero.html`) but serve
   different structural roles.

   **`components/hero.html` context contract** — both `HeroBlock.get_context()`
   and any `HeroMixin` page's `get_context()` MUST pass a `hero` dict with
   exactly these keys:
   ```python
   context["hero"] = {
       "headline": str | None,       # displayed h1; falls back to page.title in template
       "copy": RichText | str | None,# supporting copy
       "copy_is_block": bool,        # False = use |richtext filter; True = use {% include_block %}
       "image": CustomImage | None,  # hero image (also video poster fallback)
       "video": Media | None,        # wagtailmedia Media instance; triggers two-column layout
       "link_text": str | None,      # CTA button label
       "link_page": Page | None,     # CTA internal page link
       "link_url": str | None,       # CTA external URL
   }
   ```
   For `HeroBlock`: `content` is a `RichTextBlock`, so `copy_is_block=False`.
   `video` is always `None` for HeroBlock (StreamField hero does not support video).
   For `HeroMixin` pages: `hero_copy` is a `RichTextField`, so
   `copy_is_block=False` there too. Set `copy_is_block=True` only if `copy` is
   a StreamField block value (not currently used anywhere).

   **Video layout**: when `hero.video` is a wagtailmedia `Media` instance, the
   template switches to a two-column responsive grid: text on the left
   (right-aligned on `md:` and up), video on the right. On mobile both columns
   are full-width with video below text. The background image overlay is hidden
   when a video is present. Poster fallback chain: wagtailmedia thumbnail →
   `hero.image` rendered at `fill-1280x720` → no poster.
8. **wtrx/ extraction readiness**: Keep `wtrx/` structured as if it will become
   a standalone pip package. All concrete page models (`HomePage`, `ContentPage`,
   `IndexPage`, `FormField`, `FormPage`) ship with their own migrations in `wtrx/`.
   Forks that need custom page types add new apps with new page types rather than
   modifying `wtrx/` models. Follow the CodeRed CMS pattern for the eventual pip
   extraction; `wtrx/` will provide the concrete models and forks will override by
   adding new page types in separate apps.
9. **SectionContentBlock for fork extensibility**: `SectionBlock.content` uses a
   named declarative `StreamBlock` subclass (`SectionContentBlock`) instead of an
   inline tuple-list. This allows fork sites to subclass `SectionContentBlock` and
   override individual child blocks (e.g. swap `CardBlock` for a site-specific
   subclass) without duplicating the full 17-entry block list. Wagtail's
   `DeclarativeSubBlocksMetaclass` merges parent and child `declared_blocks` via
   the MRO, so a subclass only needs to redeclare the block(s) it wants to change.
   The same metaclass pattern works for `BodyStreamBlock` (override individual
   block attributes) and `CardGridBlock` (override the `cards` ListBlock).

## Error Handling

- Use Wagtail's built-in validation for blocks (`clean()` method on StructBlock).
- `ButtonBlock`: Validate exactly one of `link_page` or `link_url` is set.
- `SignupBlock`/`DonateBlock`: Validate required fields per platform variant.
- Settings fallbacks: If a setting is not configured, degrade gracefully
  (e.g., no logo = no logo rendered, not an error).
- AJAX form submission: Return JSON `{ "success": true }` or
  `{ "success": false, "errors": {...} }`. Handle network errors client-side.

## Testing

- Tests live in each app's `tests/` directory (e.g., `wtrx/tests/`).
- Test paths use the `wtrx` prefix: `wtrx.tests.test_blocks`.
- Test blocks in isolation: instantiate, call `clean()`, verify validation.
- Test page models: use `WagtailPageTestCase`.
- Test settings: verify defaults, verify admin override behavior.
- Test templates: use Django's `SimpleTestCase` with `assertContains` /
  `assertTemplateUsed`.

## Common Pitfalls

1. **DB access at import time**: Never query the database (including via
   `IntegrationSettings.for_site(...)`) at class-definition or module-import
   time. Django's ORM is not available when models are first loaded. Always
   defer DB reads to request time (e.g., inside a view, hook, or `get_context()`).

2. **FormPage MRO**: Always declare `FormPage` as
   `class FormPage(BasePage, AbstractEmailForm)` — BasePage first. Swapping the
   order breaks MRO. Explicitly define `content_panels` on `FormPage` — do NOT
   inherit it. Python's MRO will resolve to `BasePage.content_panels` and drop
   all email form fields. Start from `AbstractEmailForm.content_panels` and
   append all form panels. See PLAN.md for the exact pattern.

   Also define a companion `FormField(AbstractFormField)` model with a
   `ParentalKey` to `FormPage` and `related_name="form_fields"` — this is
   required for the form builder to work.

3. **`TranslatableMixin` on `BasePage` — DO NOT add it**: In Wagtail 7,
   `TranslatableMixin` is already in `Page.__mro__` via `AbstractPage`. Adding
   it explicitly causes `TypeError: Cannot create a consistent MRO`:
   ```python
   # WRONG — causes MRO error in Wagtail 7:
   class BasePage(TranslatableMixin, Page): ...

   # CORRECT:
   class BasePage(Page): ...
   ```
   `wagtail-localize` correctly detects `BasePage` as translatable because
   `TranslatableMixin in BasePage.__mro__` is `True` through the inherited chain.

   For `FormPage(BasePage, AbstractEmailForm)`, the full MRO resolves correctly
   without needing `TranslatableMixin` listed anywhere. Run `make migrate` (or
   `python manage.py makemigrations --check`) after adding any new page model.

4. **`hide_from_search` not `search_appearance`**: The field controlling search
   visibility on `BasePage` is named `hide_from_search` (boolean, default False).

5. **`static_compiled/` is committed**: The Tailwind CLI output directory
   `static_compiled/` is intentionally committed to the repo so that forked
   client sites have working CSS/JS immediately without needing to run
   `npm install` and `npm run build` first.

6. **`SocialLinkBlock` must be a named class**: Do not use an anonymous
   StructBlock inline in `SocialSettings.social_links`. Define
   `class SocialLinkBlock(blocks.StructBlock)` explicitly so it serializes
   correctly in migrations and the Wagtail editor.

7. **Wagtail settings base class**: Use `BaseSiteSetting` (not `BaseSetting`).
   `BaseSetting` was renamed in Wagtail 4.x. The correct import is:
   `from wagtail.contrib.settings.models import BaseSiteSetting, register_setting`

8. **Wagtail settings access in templates**: The `wagtail.contrib.settings.context_processors.settings`
   context processor is registered in `settings/base.py`, so `settings.<app_label>.ModelName`
   is available in all templates automatically. Do NOT use `SettingProxy` directly —
   it is an internal Wagtail API, not public. Use the context variable or the
   `{% load wagtailsettings_tags %}{% get_settings %}` tag for explicit access.

9. **`admin_form_fields` on the concrete Image class**: Define `admin_form_fields`
   explicitly on `CustomImage` using `Image.admin_form_fields` as the base — do NOT
   copy the tuple verbatim or rely on inheritance from `AbstractImage`. This ensures
   future Wagtail updates to the base field list are inherited automatically. Only
   append fields that are actually defined on `CustomImage` itself:
   ```python
   class CustomImage(AbstractImage):
       credit = models.CharField(max_length=255, blank=True)
       admin_form_fields = Image.admin_form_fields + ("credit",)
   ```
   Note: `description` is already part of `Image.admin_form_fields` in Wagtail 7 —
   do not append it again.

10. **Choices constants must be module-level**: If you use `gettext_lazy` in
    field `choices`, define the choices list at module level (outside any class
    body). Choices defined inside a class body with `gettext_lazy` cause migration
    serialization failures because Django cannot serialize lazy translations in
    that context at migration time.

11. **`wagtail.search.index` vs `modelsearch`**: In Wagtail 7.3+, `wagtail.search`
    was partially extracted into a separate `modelsearch` package. Migrations
    generated on Wagtail 7.3+ will import `wagtail.search.index` (the real module
    is there), but you'll also see `modelsearch` as a listed dependency in some
    environments. Both are correct depending on the Wagtail version.

12. **Never hand-write migrations**: Always use `python manage.py makemigrations`.
    Hand-written migrations drift from what Django actually generates and cause
    subtle errors. After adding or changing model fields, run:
    ```bash
    python manage.py makemigrations
    python manage.py migrate
    python manage.py test wtrx wagtail_wtr
    ```

13. **Page models need explicit `template`**: Wagtail derives the default template
    path as `<app_label>/<model_snake_case>.html`. Because the app label is `wtrx`,
    Wagtail would look for `wtrx/home_page.html`. All page templates live in
    `wtrx/templates/wtrx/pages/`. Every concrete page model
    **must** declare:
    ```python
    template = "wtrx/pages/<model_name>.html"
    ```
    Without this, visiting any published page raises `TemplateDoesNotExist`.

14. **Django `{# ... #}` comments do NOT suppress template tags on inner lines**:
    Django's `{# comment #}` syntax only works reliably on a single line. When a
    `{# ... #}` block spans multiple lines, Django still parses and compiles any
    `{% ... %}` template tags that appear between the opening `{#` and closing `#}`.
    This means a seemingly-commented-out `{% include "foo.html" %}` will still
    execute, causing silent bugs or `RecursionError` if the included template is the
    current one. The text between `{#` and `#}` also renders as visible output in
    the browser. Always use `{% comment %}...{% endcomment %}` for multi-line
    comments that contain example template code:
    ```django
    {# Short single-line comment — safe #}

    {% comment %}
    Multi-line comment. Any {% include %} or {% block %} tags here
    are safely suppressed and will not render as visible text.
    {% endcomment %}
    ```

15. **Site name in templates — use `{% wagtail_site %}`**: `settings.WAGTAIL_SITE_NAME`
    is a Django settings variable used only by Wagtail's admin interface. It is NOT
    accessible as `{{ settings.WAGTAIL_SITE_NAME }}` in templates — the Wagtail
    settings context processor only exposes registered `BaseSiteSetting` models.
    To get the site name in templates, use:
    ```django
    {% load wagtailcore_tags %}
    {% wagtail_site as current_site %}
    {{ current_site.site_name }}
    ```
    In `base.html`, call `{% wagtail_site as current_site %}` once and it will be
    available in all `{% include %}`-d templates (header, footer, etc.) via context
    inheritance. The value comes from the Wagtail `Site` model in the database
    (set in Wagtail admin under Settings → Sites).

16. **`AnchorLinkBlock` must be a named class**: Do not use an anonymous StructBlock
    inline for anchor links in `NavigationSettings.primary_navigation` or
    `FooterColumnBlock.links`. Define `class AnchorLinkBlock(blocks.StructBlock)`
    explicitly at module level so it serializes correctly in migrations and the
    Wagtail editor. The same rule applies to all StructBlock subclasses used in
    StreamField definitions on settings models.

17. **Footer layout choices must be module-level**: `FOOTER_LAYOUT_CHOICES` (and any
    other `choices=` list that uses `gettext_lazy`) must be defined at module level
    in `site_settings.py`, not inside a class body. Django cannot serialize lazy
    translations at class-definition time and will raise a `MigrationError`. This is
    a special case of pitfall #10.

18. **`collapse_desktop_menu` is CSS-only**: The `NavigationSettings.collapse_desktop_menu`
    boolean controls whether the desktop nav is hidden and the hamburger is shown at
    all breakpoints. This is implemented purely with Tailwind responsive classes in
    `header.html` — when `collapse_desktop_menu` is True, remove `md:hidden` from
    the hamburger and menu panel so they display at all sizes. The existing
    `mobile-menu.js` is breakpoint-agnostic and requires zero JS changes.

19. **Transparent header is `HomePage` only**: The `use_transparent_header` boolean
    field lives on `HomePage`, not on `HeroMixin`. Only the home page can opt into
    a transparent/overlay header. `HeroMixin` subclasses always use the normal
    header. Pass `ctx["transparent_header"] = self.use_transparent_header` in
    `HomePage.get_context()`.

    When `transparent_header` is True, `header.html` automatically switches to the
    `BrandingSEOSettings.dark_logo` — no separate toggle is needed. The logo swap
    logic lives entirely in the template.

20. **Social display toggles live on `SocialSettings`**: The `show_in_header` and
    `show_in_footer` booleans that control where social icons appear are fields on
    `SocialSettings` — not on `NavigationSettings` or `FooterSettings`. Social icon
    placement in the header follows this rule:
    - **Desktop**: icons always appear in the **visible header bar** (`hidden md:flex`)
      when `show_in_header` is True, regardless of `collapse_desktop_menu`.
    - **Mobile**: icons appear in the **menu panel** only (the panel is always
      `md:hidden` on mobile, opened by the hamburger).
    Always guard social icon rendering with
    `{% if social.show_in_header and social.social_links %}` (header) and
    `{% if social.show_in_footer and social.social_links %}` (footer).

21. **Action Network embed — URL-based, no AN CSS**: `SignupActionNetworkBlock`
    accepts a full AN URL (`https://actionnetwork.org/forms/your-slug`), not a
    manual action-type + UUID. The `parse_action_network_url()` helper in
    `blocks/__init__.py` extracts the action type and slug. Only `/forms/` is
    supported initially; extend `ACTION_NETWORK_URL_TYPES` for other types.
    Key implementation details:
    - **AN CSS is loaded** — `style-embed-v3.css` is loaded by the template
      and handles structural layout (float-labels, country selector, spinner,
      two-column form layout). Custom styles scoped under `.wtr-action-network-embed`
      in `static_src/css/main.css` override only visual tokens (fonts, colours,
      submit button) and hide AN branding. **Do not remove the `<link>` tag** —
      the form layout will break without it.
    - **Embed pattern**: `<script src='https://actionnetwork.org/widgets/v6/form/{slug}?format=js&source=widget'>`
      + `<div id='can-form-area-{slug}'>`. Note the plural-to-singular mapping
      (`/forms/` URL → `form` embed type) and the div ID format `can-{type}-area-{slug}`.
    - **Slug validation**: `parse_action_network_url()` validates slugs against
      `^[a-z0-9][a-z0-9\-]*$` to prevent JS/HTML injection via the template.
    - **Success message**: optional `SuccessMessageBlock` (StreamBlock: text, image,
      button, quote). When provided, inline JS in the
      template uses a `MutationObserver` to detect AN's `.can_thank_you_wrap` and
      replace it with the custom message. The JS targets the embed by its unique
      `can-{type}-area-{slug}` ID + `.closest()`, so multiple AN blocks on one
      page work correctly.
    - **`get_context()` wraps parsing in try/except** to prevent 500 errors at
      render time if a bad URL somehow gets saved.
    - **Template guards**: embed `<script>`/`<div>` are wrapped in
      `{% if action_type and slug %}` to prevent broken markup.
    - **`<noscript>` fallback**: links to the original AN form URL.

22. **`WAGTAILFRONTENDCACHE` is configured in `production.py`, not `base.py`**:
    The `WAGTAILFRONTENDCACHE` dict is set conditionally in `production.py` based
    on the `CLOUDFLARE_BEARER_TOKEN` and `CLOUDFLARE_ZONE_ID` environment variables.
    It is intentionally absent from `base.py` and `dev.py`. All cache functions in
    `wtrx/cache.py` check `getattr(settings, "WAGTAILFRONTENDCACHE", None)` and
    are silent no-ops when it is unset. Never read `WAGTAILFRONTENDCACHE` at module
    import time — always read it inside the function body.

23. **`Page.specific` is a `cached_property`, not a method**: In Wagtail,
    `page.specific` is a `cached_property` that returns the concrete subclass
    instance. It must be accessed as `page.get_parent().specific` (no parentheses).
    Calling `page.get_parent().specific()` raises `TypeError: '<ModelClass>' object
    is not callable` at runtime — this is silently swallowed if you have a bare
    `except Exception: pass` block, making it a particularly sneaky bug.
    Always write `.specific` without parentheses.

24. **Cache signal patch target**: When testing that a settings model save triggers
    `purge_all()`, patch `wtrx.signals.purge_all` (the imported name in the signals
    module), not `wtrx.cache.purge_all`. The signal handler holds the reference it
    imported at module load time; patching the original module has no effect on
    already-imported names.

    Similarly, when testing `PURGE_ALL_HANDLERS` dispatch, patch the dict itself
    using `patch.dict(PURGE_ALL_HANDLERS, {...})` rather than patching the handler
    function by name — the dict was built at import time with direct function
    references, so patching the module-level name does not update the dict entry.

## Git Conventions

- Branch from `main`. Descriptive branch names: `feature/signup-block`,
  `fix/hero-image-fallback`.
- Commit messages: imperative mood, concise. E.g., "Add CardGridBlock with
  auto-responsive columns" not "Added card grid block".
- Do not commit `node_modules/`. Do commit `static_compiled/`.

## Documentation Maintenance

Keep the following files up to date whenever relevant changes are made:

- **`PLAN.md`** — update the frontend build section, phases, and architecture notes
  whenever the tech stack, file structure, or implementation decisions change.
  **Phase status must be kept current**: mark phases `✅ COMPLETE`, `🔄 IN PROGRESS`,
  or plain (not started). Within an in-progress phase, use `[x]` / `[ ]` checkboxes
  to track individual items. Update phase status in the same commit as the work.
- **`AGENTS.md`** — update build commands, pitfalls, and architecture rules to match
  the current state of the repo. This file is the source of truth for agents.
- **`README.md`** — update commands, stack description, and project structure whenever
  anything user-facing changes.

These files should never fall out of sync with the actual repo. Update them in the
same commit as the code change they describe.

## Code Review Requirement

**Before creating any commit**, two reviews are required in this order:

1. **Agent code review** — Run the `code-reviewer` agent on all changed files
   using the Task tool with `subagent_type: "code-reviewer"`. Provide:
   - A summary of what was built and why
   - The full list of files changed
   - Any specific areas of concern or uncertainty

   Address any issues the reviewer raises before proceeding.

2. **Human code review** — Present the changes to the user and explicitly ask
   them to review. Wait for their sign-off before committing.

Only create the commit after both reviews are complete and any issues have
been addressed. This applies to all commits, including small fixes.

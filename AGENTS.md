# AGENTS.md -- wagtail-wtr

Guidelines for AI coding agents working in this repository.

## Project Overview

wagtail-wtr is the Wagtail CMS platform used at With the Ranks for campaign,
nonprofit, and organizer websites. It's a working Django/Wagtail project —
not a `wagtail start --template`. New client sites fork or clone this repo.

The core reusable app lives at `wtrx/` (repo root, sibling to `wagtail_wtr/`)
and is designed for eventual extraction to a standalone pip package
(`wagtail-wtrx`), following a pattern similar to CodeRed CMS.

See `PLAN.md` for the full specification and architectural decisions.

## Repository Structure

```
wagtail-wtr/
├── wtrx/                   # Core reusable app (future pip package)
│   ├── blocks/             # StreamField blocks (one file, __init__.py, organized by comment-banner category)
│   ├── integrations/       # One module per pre-set integration + the registry
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
│   ├── settings/{base,dev,production}.py
│   ├── urls.py
│   └── wsgi.py
├── templates/              # Fork override templates (empty in upstream; forks shadow wtrx/ templates here)
├── static_src/             # Frontend source (Tailwind, JS, fonts)
├── static_compiled/        # Tailwind CLI output (gitignored; built at deploy time)
├── fixtures/
├── manage.py / pyproject.toml / Makefile / Dockerfile
├── render.yaml             # Render Blueprint (Docker runtime + PostgreSQL)
├── bin/{start.sh,provision.sh}
└── .env.example
```

- `wtrx/blocks/` is one file (`__init__.py`) organized by comment-banner
  category (Content/Cards/Layout/Actions) rather than the per-category split
  the directory name suggests — add new blocks under the matching banner.
- `templates/` (project root) is checked first by Django's `DIRS` resolver —
  forks shadow `wtrx/` defaults here.
- `static_compiled/` is gitignored build output — never commit it.

## How to Dev and Test This Repo

All commands run from the repo root.

### Python (Django)

```bash
make venv && source .venv/bin/activate
make migrate                 # Run migrations
make test                    # Run all tests
make dev                     # Dev server at localhost:8000 + Tailwind watcher
make dev-server               # Dev server only
make createsuperuser
make setup                   # Interactive initial setup

python manage.py test wtrx wagtail_wtr                               # all tests
python manage.py test wtrx.tests.test_images                        # single module
python manage.py test wtrx.tests.test_images.TestObjectPositionStyle # single class
```

### Migrations

Never hand-write them. After model changes:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py test wtrx wagtail_wtr
```

### Frontend (CSS/JS)

```bash
npm install                  # once only
make build                   # Dev build (CSS + JS + fonts + images)
make build-prod               # Production build (CSS minified)
make watch                   # CSS watch mode
```

`static_compiled/` is gitignored — run `make build` after cloning. In
production the Docker Stage 1 build generates it. Font source lives in
`static_src/fonts/` (this fork self-hosts Klima — see pitfall #37). JS lives
in `static_src/js/`, copied verbatim to `static_compiled/js/`, loaded via
`<script type="module">` — no bundler.

### Visual checks (Playwright)

Playwright **is installed and works headless** in this environment, including
agent sandboxes — it's just easy to miss because it's in *user*
site-packages, not `.venv`, and Chromium isn't on `PATH`. Always use bare
`python3` for Playwright scripts, never the venv interpreter.

```bash
python3 -c "import playwright; print(playwright.__file__)"
ls ~/.cache/ms-playwright
```

Recipe: serve on a port that won't collide with an existing dev server, then
screenshot with `page.locator(sel).screenshot()` at 1512px wide (Figma's
frame width, so it's pixel-comparable to a Figma node render):

```bash
source .venv/bin/activate && set -a && source .env && set +a
python manage.py runserver 8021 --noreload &
python3 - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1512, "height": 889})
    pg.goto("http://127.0.0.1:8021/", wait_until="networkidle", timeout=60000)
    pg.wait_for_timeout(1500)
    pg.locator(".wtr-hero").screenshot(path="/tmp/hero.png")
    b.close()
EOF
```

**Measure, don't eyeball, when a layout is off.** `page.evaluate()` over
`getComputedStyle`/`getBoundingClientRect` gives exact widths/gaps/flex
bases — the only practical way to debug fetched third-party markup (e.g.
ActionKit), whose real dimensions aren't knowable from the template alone.
Reviewing a Figma alignment change without a screenshot is not a review.

### Docker

```bash
docker build -t wagtail-wtr .
make load-data   # migrate + loaddata fixtures/demo.json + collectstatic
```

## Code Style

### Python

- PEP 8, 4-space indent, max line length 119.
- Import order: stdlib, Django, Wagtail, third-party, local (`wtrx` prefix
  for cross-app imports).
- Double quotes for human-readable strings (help_text, verbose_name); single
  quotes for identifiers/keys.
- One model per logical concern; abstract models for shared behavior.
  `related_name='+'` on FKs that don't need reverse relations.
  `on_delete=models.SET_NULL` for optional image/page FKs.
- Every block class needs a docstring and `class Meta` with `icon` and
  `template` pointing to `wtrx/components/streamfield/blocks/<name>.html`
  (relative to the templates root, no `templates/` prefix).
- Module-level constants for field lengths and richtext feature lists — never
  hardcode magic numbers.
- Naming: models PascalCase, fields snake_case, block classes end in
  `Block`, settings models end in `Settings`, mixins end in `Mixin`.
- `gettext_lazy` (as `_`) for all translatable strings in Python — defaults,
  help_text, verbose_name, choice labels.
- Type hints not required for Django/Wagtail models/blocks; use them for
  utility functions.

### Templates (HTML)

- All user-facing UI strings use `{% trans %}`/`{% blocktrans %}` (with
  `{% load i18n %}`) — button defaults, pagination, errors, form feedback.
  Editor-entered content is handled by wagtail-localize instead.
- Tailwind: semantic tokens only, never raw colors (`bg-primary-600` not
  `bg-blue-600`; `error-*`/`success-*`/`warning-*` for status, never raw
  red/green/yellow).
- Every major layout region/block needs a semantic `wtr-<name>` class on its
  outermost element (`wtr-header`, `wtr-hero`, `wtr-card-grid`,
  `wtr-donate`, etc.) — these carry no styles, they're stable hooks for
  client theme overrides. Always additive to Tailwind utilities, never a
  replacement.
- Components: `wtrx/templates/wtrx/components/` (blocks under
  `.../streamfield/blocks/`). Fork overrides: `templates/` (project root).
- 4-space indent.

### JavaScript

Vanilla JS only, no frameworks. Class-based components, selector-based init.
ES modules, 4-space indent, semicolons required.

### CSS

- Entry point `static_src/css/main.css`, Tailwind v4 (`@import 'tailwindcss'`,
  no `@tailwind` directives, no `tailwind.config.js` — TW4 doesn't use it).
- Built with `@tailwindcss/cli` → `static_compiled/css/main.css` (gitignored).
- Plugins (`@tailwindcss/typography`, `@tailwindcss/forms`) declared in
  `main.css`.
- Theme tokens (`--color-*`, `--font-*`) live in `static_src/css/theme.css`
  under `@theme {}`, imported by `main.css` before `tailwindcss`. Named
  presets (`[data-theme="grassroots"]`, etc.) also live there.
- Minimize custom CSS; prefer Tailwind utilities. Component classes use the
  `@utility` directive (TW4's replacement for `@layer components/utilities`).

## Architecture Rules

1. **`wtrx/` is self-contained**: all page models and the `search()` view
   live in `wtrx/`, the only project app. No separate `users/` app, no
   `AUTH_USER_MODEL` override — use `django.contrib.auth.models.User`
   directly. Forks needing custom user fields add their own app with an
   `AbstractUser` subclass in their fork's settings, not upstream.
2. **No raw columns/grids in blocks**: layout is through opinionated
   composite blocks (`SectionBlock`, `CardGridBlock`, `CalloutBlock`).
   Editors shouldn't be able to build arbitrary column layouts.
3. **i18n from day one**: every hardcoded UI string is translatable
   (`{% trans %}` in templates, `gettext_lazy` in Python) from the start.
4. **`HeroMixin` vs `HeroBlock`**: `HeroMixin` is a page-model mixin
   providing a dedicated hero at the top of a page (`HomePage`,
   `ContentPage`, etc.); `HeroBlock` places a hero-style section *within*
   the body StreamField. Both render `components/hero.html` and must pass a
   `hero` context dict with exactly these keys: `variant`, `pre_header`,
   `headline`, `copy`, `copy_is_block`, `image`, `video`, `image_caption`,
   `banner_color`, `cta`, `tag`, `tag_url`, `author`, `published_at`,
   `minimal`, `in_body`. `in_body=True` only for `HeroBlock`, and it no
   longer changes the gutter — every hero and every full-width block now
   shares one container, `mx-auto max-w-[1500px] px-4` (flat 16px at every
   breakpoint). The nav (`header.html`) deliberately still steps
   `px-4 sm:px-6 lg:px-8`, so from `sm:` up the header's content is inset
   8–16px further than the hero beneath it. `pre_header` is an uppercase
   overline above the headline, editable on `HomePage` only
   (`HeroMixin.hero_panels`; `banner_hero_panels` omits it, and
   `BannerHeroMixin`/`HeroBlock` pin it `None`). In the "full" variant it
   sits on a translucent dark scrim (`.wtr-hero-pre-header` in `main.css`,
   which owns its padding and 6px radius) for contrast against the
   background photo — the hero's own gradient fades to transparent at the
   top and so does not cover this band. Deliberately not the `eyebrow`
   pill of `FeaturePanelBlock`/`SignupActionKitBlock`: an opaque fill at
   `wtr-btn`'s radius reads as a CTA, and `hero.cta` renders a real button
   just below it. The rule is scoped `.wtr-hero:not(.wtr-hero-banner)` —
   the banner variant's text column sits on a flat `banner_color` fill and
   flips to `text-dark` on a light banner, where a dark scrim would be
   wrong. It is the site's only non-heading user of `font-heavy`
   (pitfall #34). `hero` and `quote` must stay in each page
   template's full-bleed block-type list (both own a `max-w-[1500px]`
   wrapper that's unreachable inside the shared body column). When
   `hero.video` is a wagtailmedia `Media`, the template switches to a
   two-column layout (text left, video right; stacked on mobile), hiding
   the background-image overlay. Poster fallback: wagtailmedia thumbnail →
   `hero.image` at `fill-1280x720` → none. `image_caption` is an optional
   caption pill overlaid at the bottom of whichever of `image`/`video` is
   showing (`.wtr-image-caption`, same chrome as `SignupActionKitBlock`/
   `ImageBlock`) — `HeroBlock` has no video, so it's image-only there.
   "banner" variant only: `HomePage` (the only "full" variant page)
   omits the field from `hero_panels`, and the "full" section of
   `hero.html` has no caption chrome at all.
5. **`wtrx/` extraction readiness**: concrete page models ship their own
   migrations in `wtrx/`. Forks needing custom page types add new apps
   rather than modifying `wtrx/` models directly.
6. **`SectionContentBlock` for fork extensibility**: `SectionBlock.content`
   uses a named declarative `StreamBlock` subclass instead of an inline
   list, so forks can subclass it and override individual child blocks —
   Wagtail's `DeclarativeSubBlocksMetaclass` merges `declared_blocks` via
   MRO. Same pattern applies to `BodyStreamBlock` and `CardGridBlock.cards`.
7. **Block visibility via picker filtering, not import-time DB reads**: all
   Signup/Donate variants stay registered in `BodyStreamBlock`/
   `SectionContentBlock` always; `IntegrationGatedStreamBlockMixin`
   (`wtrx/blocks/__init__.py`) hides disabled-integration variants from the
   "Add block" picker at request time by overriding `sorted_child_blocks()`
   — it never touches `child_blocks`, so previously-placed blocks keep
   rendering even if the integration is later disabled. Filtering
   `sorted_child_blocks()` alone breaks the *editor* for already-placed
   gated blocks (see pitfall #52) — it also needs the companion telepath
   `GatedStreamBlockAdapter`. Request access inside a block goes through
   `wtrx/request_context.py`'s `ContextVar`, populated by
   `CurrentRequestMiddleware`. Never read the DB at class-definition/import
   time.
8. **Integrations framework**: Settings > Integrations
   (`IntegrationSettings.integrations`) lets an editor add any number of
   pre-set integrations (ActionKit, Fundraise Up, ActBlue, Action Network),
   each independently enabled/configured.
   - `wtrx/integrations/registry.py` holds pure-Python `IntegrationType`
     metadata (slug, category, `content_block_names`, optional
     `head_html_field`) — safe at import time.
   - One module per integration (config `StructBlock` + `register_integration()`).
   - `IntegrationsStreamBlock` (`site_settings.py`) is the named
     `StreamBlock` building the "Add integration" UI.
   - To add an integration: write its module, add one line to
     `IntegrationsStreamBlock`, and register its content block on
     `BodyStreamBlock`/`SectionContentBlock` if it has one.
   - Read config via `IntegrationSettings.get_integration_config(slug)` —
     never reach into `.integrations` directly.
   - `IntegrationType.default_enabled=True` (only `wagtail_forms` sets it)
     gates a built-in block the same way without changing its default
     visibility: `is_integration_enabled(slug)` returns the registry
     default only when *no entry at all* exists — an explicit entry always
     wins. A `default_enabled=True` slug with no entry also yields
     automatically to any genuine third-party integration explicitly
     enabled in the same `category` (e.g. enabling ActionKit hides Wagtail
     Forms), via `_explicit_entry_enabled()` — this check explicitly skips
     other `default_enabled=True` siblings to avoid mutual recursion.
   - `DonateBlock`/`actblue` is intentionally the generic/URL-based donate
     integration (not given its own toggle, since it already sources its
     URL from that config entry) — distinct from the true API integration
     `DonateFundraiseUpBlock`/`fundraiseup`.
9. **wagtail-ai integration**: AI-assist buttons are opt-in per field via
   drop-in panels (`AITitleFieldPanel`/`AIDescriptionFieldPanel`/
   `AIFieldPanel` from `wagtail_ai.panels`, used in `BasePage.title_panels`/
   `promote_panels`). Notes:
   - Can't reach inside StreamField blocks (StructBlock subfields render
     through block-form machinery) — the only StreamField hook is
     `wagtail_ai.blocks.ai_image_block()` on `ImageBlock`.
   - `WAGTAIL_AI` settings need both `BACKENDS` (Draftail toolbar) and
     `PROVIDERS` (panel actions) — omitting `PROVIDERS` silently falls back
     to a deprecated hardcoded-`openai` path that only errors when clicked.
   - `wtrx/static/wtrx/admin/wagtail-ai-context-fix.js` patches a missing
     `await` in wagtail-ai's bundled JS (remove once upstream fixes it);
     `pin-draftail-toolbar.js` defaults the toolbar to pinned.
   - `{% wagtailuserbar %}` must stay in `base.html` — it registers the
     preview-content-extraction bridge that live preview, AI title/
     description, and Wagtail's native Content Checks panel all depend on.
   - Image title/description AI buttons need a template override
     (`templates/wagtailimages/images/edit.html`), not a panel swap — the
     Images admin edit view is a plain `ModelForm`, not the Panel pipeline.
   - "Get content feedback" (Checks side panel) needs
     `AgentSettings.content_feedback_prompt` non-empty — Anthropic's API
     rejects an empty `messages` list, and this is the only prompt field
     with no default.
   - `llm-anthropic` must stay pinned compatible with the installed
     `anthropic` SDK major (`llm-anthropic>=0.27,<0.28` for `anthropic` 1.x)
     — a signature-drift mismatch surfaces as `TypeError: unexpected
     keyword argument 'temperature'` from the Draftail AI toolbar actions.

10. **Multilingual is one page tree per language, under Root**: `Home (en)`
    at `/`, `Home (pt)` at `/pt/`, `Home (fr)` at `/fr/` — Wagtail's own
    model, `WAGTAIL_I18N_ENABLED = True`, `LocaleMiddleware` and
    `i18n_patterns` all kept. Language is the axis that changes the URL; an
    English-language *region* (`/canada/`) is an ordinary section under the
    English Home and has nothing to do with locales. A translated page is a
    real page linked to its source by `translation_key`, so it can carry its
    own slug (`/about/` → `/pt/sobre-nos/`) and a language tree can hold
    pages that exist in that language only. See pitfall #65 for why the
    alternative (regional subtrees under Home at `/brasil/`, flag off) was
    rejected.

## Error Handling

- Use Wagtail's built-in `clean()` validation on blocks.
- `ButtonBlock`: exactly one of `link_page`/`link_url`.
- `SignupBlock`/`DonateBlock`: validate required fields per platform variant.
- Settings fallbacks degrade gracefully (no logo = no logo, not an error).
- AJAX forms return `{"success": true}` or `{"success": false, "errors": {...}}`.

## Testing

Don't re-run the full suite after every edit — it takes ~16s plus DB setup
and most changes here are templates/CSS that no test touches. Run it once as
a final check, or after any change to models/blocks/migrations/template
tags/views/settings. A single module
(`python manage.py test wtrx.tests.test_blocks`) is a better mid-session
check.

- The dev server started with `--noreload` caches templates — restart it
  before screenshotting/measuring after a template edit.
- Never `pkill -f "manage.py runserver"` — other sessions match that
  pattern too. Kill your own server by its PID, use a port you picked
  yourself. Concurrent test runs also collide on the single
  `test_wtr350` database.
- Tests live in each app's `tests/` dir, path-prefixed `wtrx.tests.*`.
- Test blocks in isolation (instantiate, `clean()`); pages with
  `WagtailPageTestCase`; templates with `SimpleTestCase` + `assertContains`.

## Common Pitfalls

1. **DB access at import time**: never query the DB at class-definition/
   module-import time — defer to request time (view, hook, `get_context()`).
2. **`FormPage` MRO**: `class FormPage(BasePage, AbstractEmailForm)` —
   `BasePage` first. Explicitly define `content_panels` (start from
   `AbstractEmailForm.content_panels` + form panels) — inheriting it drops
   the email form fields. Needs a companion `FormField(AbstractFormField)`
   with a `ParentalKey` to `FormPage`, `related_name="form_fields"`.
3. **Don't add `TranslatableMixin` to `BasePage`** — it's already in
   `Page.__mro__` via `AbstractPage` in Wagtail 7; adding it explicitly
   raises `TypeError: Cannot create a consistent MRO`.
4. **`hide_from_search`**, not `search_appearance`, is the field name.
5. **`static_compiled/` is gitignored** — run `npm install && make build`
   after cloning, or the dev server has no CSS/JS/fonts.
6. **`SocialLinkBlock` must be a named class**, not an anonymous inline
   StructBlock, so it serializes correctly in migrations. Same rule for
   `AnchorLinkBlock` (nav/footer links) and any other StructBlock used in a
   settings-model StreamField.
7. **Use `BaseSiteSetting`**, not `BaseSetting` (renamed in Wagtail 4.x).
8. **Settings in templates**: use the `settings.<app_label>.ModelName`
   context variable (via the registered context processor) or
   `{% get_settings %}` — never `SettingProxy` directly (internal API).
9. **`CustomImage.admin_form_fields`**: build from `Image.admin_form_fields
   + (...)`, appending only fields actually on `CustomImage` — don't copy
   the tuple verbatim, and don't re-append `description` (already included
   in Wagtail 7).
10. **`gettext_lazy` in `choices=` must be module-level**, not inside a
    class body — Django can't serialize lazy translations there at
    migration time (same rule for any `*_CHOICES` list, e.g.
    `FOOTER_LAYOUT_CHOICES`).
11. **`wagtail.search.index` vs `modelsearch`**: both are correct depending
    on Wagtail version (7.3+ partially extracted search into `modelsearch`).
12. **Never hand-write migrations** — always `makemigrations`.
13. **Page models need explicit `template = "wtrx/pages/<model_name>.html"`**
    — Wagtail's default `wtrx/<model_snake_case>.html` guess doesn't match
    where templates actually live.
14. **Django `{# ... #}` doesn't suppress `{% %}` tags across multiple
    lines** — a "commented out" multi-line `{% include %}` still executes.
    Use `{% comment %}...{% endcomment %}` instead.
15. **Site name in templates**: `{% wagtail_site as current_site %}` then
    `{{ current_site.site_name }}` — `settings.WAGTAIL_SITE_NAME` is a
    Django settings var, not exposed to templates.
16. **`collapse_desktop_menu` is CSS-only**: Tailwind responsive classes in
    `header.html` toggle whether the desktop nav vs. hamburger shows at all
    breakpoints; `mobile-menu.js` needs no changes.
17. **Transparent header is `HomePage`-only** (`use_transparent_header`,
    not on `HeroMixin`). When true, `header.html` auto-swaps to
    `BrandingSEOSettings.dark_logo`.
18. **Social display toggles live on `SocialSettings`**
    (`show_in_header`/`show_in_footer`), not Navigation/FooterSettings.
    Desktop icons show in the visible header bar; mobile icons show only in
    the menu panel.
19. **Action Network embed is URL-based**: `SignupActionNetworkBlock` takes
    a full AN URL, parsed by `parse_action_network_url()`
    (`blocks/__init__.py`, only `/forms/` supported, slug validated against
    `^[a-z0-9][a-z0-9\-]*$`). AN's `style-embed-v3.css` `<link>` is required
    for layout — don't remove it. Optional success-message swap uses a
    `MutationObserver` on `.can_thank_you_wrap`, scoped by the embed's
    unique `can-{type}-area-{slug}` ID. `get_context()` wraps parsing in
    try/except; template guards the embed behind `{% if action_type and slug %}`.
20. **`WAGTAILFRONTENDCACHE`** is set conditionally in `production.py` only
    (absent from `base.py`/`dev.py`); `wtrx/cache.py` functions no-op via
    `getattr(settings, "WAGTAILFRONTENDCACHE", None)` — read it inside the
    function body, never at import time.
21. **`Page.specific` is a `cached_property`, not a method** — no
    parentheses (`page.get_parent().specific`). Calling it as `.specific()`
    raises `TypeError`, easily swallowed by a bare `except Exception: pass`.
22. **Cache signal test patch targets**: patch `wtrx.signals.purge_all`
    (the imported name), not `wtrx.cache.purge_all`. Patch
    `PURGE_ALL_HANDLERS` via `patch.dict(...)`, not the handler function by
    name — the dict holds direct references built at import time.
23. **Validator functions referenced by historical migrations can't move
    without a re-export shim**: migrations serialize `validators=[...]` as
    a frozen dotted path. Keep a
    `# noqa: F401 -- referenced by historical migration <name>` import at
    the old location permanently if the function moves.
24. **`NavigationSettings.resolved_for_page()`** returns either the
    `NavigationSettings` instance or a `NavigationOverrideBlock`
    `StructValue` — `header.html` reads both without branching, so every
    attribute it touches (`primary_navigation`, `regional_label`,
    `root_page`, `cta_*`, `collapse_desktop_menu`) must exist on *both*.
    Django silently resolves a missing attribute to `""`, so a half-added
    field fails silently rather than raising.
25. **Regional label badge is nav-scoped**: `regional_label` comes from the
    resolved navigation (walks `path`/`depth` via `resolved_for_page()`),
    not a `HomePage` field — set per-section on a navigation override, or
    site-wide on `NavigationSettings`.
26. **Nav hover/active states** (`header.html`, Figma node 1:965): light
    headers hover `text-navy`, transparent headers hover `text-light`
    (navy is unreadable on a dark hero) — same split for the regional
    badge and logo. The logo hover uses a CSS `brightness()` filter, not a
    color swap — `<img>` is opaque to `fill`/`color`/`currentColor`
    regardless of SVG or PNG. `--color-secondary-600` is an alias for
    `--color-navy` (see #33) so nav/button/callout navy can't drift apart.
    Nav resting weight is Medium (600, `font-medium`→ remapped, see #34),
    stepping to Bold (700) only on the active item — mutually exclusive,
    never both `font-*` classes at once. Active state is an underline
    (`decoration-primary-600 decoration-[0.3em]`), not a border, doubled
    from Figma's spec because it read too thin. On a submenu the underline
    goes on the label `<span>`, not the `<button>` (would strike through
    the caret). Buttons need explicit `cursor-pointer` — TW4 preflight sets
    `button { cursor: default }`.
27. **`nav_item_is_active`** (`wtrx_tags.py`) matches sections (current
    page is/beneath the link's target), not exact pages, using a `path`
    prefix test. External/anchor links never match (no reliable way to
    tell); a submenu label itself isn't a link so a same-named page doesn't
    falsely activate it.
28. **Block picker previews need three things**:
    `templates/wagtailcore/shared/block_preview.html` (a self-extending
    override of Wagtail's own template — its mere existence is what
    switches `is_previewable` on via `template_is_overridden`, so deleting
    it silently kills every preview); a preview value, either
    `Meta.preview_value = staticmethod(fn)` (must be wrapped in
    `staticmethod()` or Wagtail binds and calls it with `self`) or
    `ContentPreviewMixin` sourced from `wtrx/previews/block_previews.json`
    (harvested via `manage.py harvest_block_previews`) — never both on one
    block; and optional layout hints as class attributes (`preview_layout`,
    `preview_target_width`, `preview_max_width`), not `Meta` fields.
29. **`ContentPreviewMixin`** revives harvested image pks with `to_python()`
    (not `normalize()`), overrides `is_previewable` as a plain `property`
    (not `cached_property` — the block instance is shared across
    StreamBlocks, so caching would freeze the answer process-wide; queries
    behind it are cached separately via `PREVIEW_LOOKUP_CACHE_TIMEOUT`).
30. **Imported pages must set `first_published_at` themselves** — Wagtail
    only populates it on admin publish, and PostgreSQL sorts NULLs first
    under `DESC`, sinking imported content beneath genuinely old pages in
    anything ordering by it (e.g. `PageCardsBlock`). Both content importers
    set it on create from the source date.
    `python manage.py backfill_first_published` repairs older imports. A
    listing's order comes from the index page's `get_listing_queryset()`
    when defined (e.g. `Blogs` orders by `published_at`), falling back to
    `first_published_at` otherwise.
31. **`WTRX_GOOGLE_SSO_ONLY` only hides the login form UI** — password auth
    (`ModelBackend`) still works via direct POST. Deliberate superuser
    fallback, not a bug.
32. **Non-hero type scale sits one notch below Figma** (deliberate — Figma's
    scale read too large against 20px body copy). Body paragraphs are
    `text-lg sm:text-xl` (20px); most headings stepped down one notch (e.g.
    section H2 64→40, card `h3` 18-24→28px flat, no `lg:` bump). Every
    `h3` site-wide is 28px, every `h4` 24px — driven by `.wtr-text-block
    h3/h4`/`.prose h3/h4` in `main.css`, not per-block overrides. Only the
    **home page hero** keeps Figma's full 96px display size (`HeroMixin`'s
    `banner` variant elsewhere is 48px). `CalloutBlock`'s body copy stays
    at 24px deliberately (pull-quote emphasis, not running text) — don't
    "fix" it to match the 20px body size. Card *listings*
    (`post_card.html`) sit at 24px vs. card *content*
    (`card.html`) at 28px, via a `heading_size` parameter each template
    takes rather than a hardcoded per-block size. `CardGridBlock`/
    `PageCardsBlock` share one `max-w-[1218px]` width, special-cased out of
    the shared body column. Inter-block spacing is `space-y-24` (96px) on
    content/post/index pages, `space-y-32` (128px) on the home page only;
    `CardCarouselBlock`'s trailing arrow row gets a `-mb-8` correction on
    the arrow row itself (not the block root — that would replace the
    loop's own margin, not shorten it). `text-sm` chrome (nav, footer,
    labels, pagination) was deliberately left alone. Before changing any
    heading/body size, check `.wtr-text-block`/`.prose` rules and the
    per-template `heading_size` params in `main.css`/block templates rather
    than guessing — this area has drifted and been corrected more than once.
33. **One shared background palette** (`BACKGROUND_COLOR_CHOICES` in
    `wtrx/blocks/__init__.py`) — every block with a background field draws
    from it (field *name* varies: `background`/`color`/`banner_color`).
    Fills live in one CSS class set, `.wtr-bg-{color}` in `main.css` (plus
    `.wtr-bg-fade-{color}` for the hero gradient) — don't reintroduce
    per-component fill sets. **Never interpolate a stored value straight
    into a class name** — always go through the `background_key` filter
    (`resolve_background()`), which maps legacy keys
    (`LEGACY_BACKGROUND_VALUES`) and falls back to `white` for anything
    unrecognised; migration `0040_unify_block_background_values` rewrote
    live data but old revisions can still resurface legacy keys on revert.
    Light/dark text branches on `background_is_light`
    (`LIGHT_BACKGROUND_COLORS = {white, light-grey}`), computed once via
    `{% with %}`, never a direct color-name comparison. `SectionBlock`
    renders as an inset rounded panel (`max-w-[1500px] px-4`, matching
    `image_block.html`'s own container/radius — see pitfall #60 for the
    single full-width container string and why the nav is no longer part of
    it) publishing `data-bg-tone` for children to invert against. `IMAGE_ALIGNMENT_CHOICES` is the same kind of shared constant
    for left/right image blocks (`QuoteBlock`, `FeaturePanelBlock`,
    `ImageCardListBlock`, `ImageTextBlock`, `DonateFundraiseUpBlock`) — the
    image column always stays the first DOM child and gets
    `md:order-2` when `alignment == 'image-right'`.
34. **Klima is self-hosted** from `static_src/fonts/klima/` with **relative**
    `url()`s in `theme.css` (not a CDN) — relative paths are load-bearing
    in production, since `CompressedManifestStaticFilesStorage` rewrites
    them at `collectstatic` time and hard-errors on anything it can't
    resolve. Only present after `make build-fonts` (part of `make build`)
    copies `static_src/fonts/` into gitignored `static_compiled/fonts/`.
    Four faces map to specific weights, and three are **remapped tokens**
    that will surprise anyone assuming Tailwind defaults: `font-medium` =
    600 (not 500), `font-semibold`/`font-bold` both = 700, and Heavy (800)
    is reachable only through `font-heavy`, a utility Tailwind generates
    from theme.css's own `--font-weight-heavy` token. **h1/h2 get Heavy,
    h3-h6 get Bold via bare element rules in `main.css`** (unlayered, so
    they beat any weight utility on a heading outright, including Tailwind
    Typography's own hardcoded prose weights) — putting a weight utility on
    a *heading* silently does nothing; add/change an unlayered element rule
    instead (`.wtr-timeline-year-label` is the worked example). A
    **non-heading** element is not covered by those rules and takes
    `font-heavy` normally: `.wtr-hero-pre-header` (a `<p>`) is the one
    element on the site that does this. Only `woff2`+
    `woff` are shipped (no `eot`/`svg`/`ttf`).
35. **Alt text is the rendition's `alt`**, not `image.title` (which
    defaults to the filename) — read via `{% image ... as img %}` then
    `img.alt`, Wagtail's own fallback chain (contextual → description →
    title). A filename showing up in alt means that image needs a
    description filled in (`/admin/images/<id>/`, wagtail-ai can generate
    one) — not a template bug, and not something to auto-suppress.
    `ImageBlock.alt_text` still wins when set. Decorative images
    (`alt="" role="presentation"`) lose `role="presentation"` the moment a
    description promotes them to content.
36. **Tailwind scans the whole tree, including harvested/fetched
    third-party markup.** `wtrx/previews/block_previews.json` (harvested
    page content, pitfall #28) once leaked ActionKit's own `text-black`
    class into the compiled bundle via a scanned string, coloring text
    black inside every live AK embed regardless of panel fill. Fixed by
    excluding the JSON from Tailwind's source (`@source not '...'` in
    `main.css`) and setting `color: inherit` on the AK wrapper's own
    `#action-form`/`.user-form`/`#unknown_user` selectors so wrapper color
    always wins. Rule going forward: scraped or fetched third-party HTML
    must never sit in Tailwind's source path.
37. **AK signup panel chrome must be checked in every background *and*
    state**, not just every fill. `SignupActionKitBlock.PANEL_TONES` maps
    fill → `.wtr-ak-on-{tone}` (white and light-grey get *different* tones
    despite both inverting text, because their field boxes need to move in
    opposite directions to stay a distinct surface). The tone class also
    rides the thank-you box, gated on `stacked` (hero's compact rendering
    sits on the hero's own scrim instead). `layout` (`columns`/`vertical`)
    is a separate axis from `stacked`/`inline` field layout — don't
    conflate them.
38. **ActionKit clears a validation error by emptying its `<ul class="ak-err">`,
    not removing it** — key error-state CSS off `:has(.ak-error)`
    (the label/input class AK does remove), never `:has(> ul.ak-err)`. AK
    also reports one field error at a time.
39. **Some block adjacencies auto-tighten** (from the page loop's
    default 96px/128px `space-y-*`) via unlayered `:has()` rules in
    `main.css`'s "Body-stack spacing" section — to 32px around `button`
    blocks and for `text` immediately before a card row, and to **40px
    after a `heading` block**. Deliberate and automatic, not
    editor-configurable, and one-directional (card-row → text stays at the
    full gap). `heading` is the one rule with no `:has()` test on what
    follows, because a section title is always followed by its own
    content. Its 40px is not a third invented number: it is
    `CardGridBlock`/`PageCardsBlock`'s own `mb-10` between their optional
    heading and their cards, which `HeadingBlock` exists to match (see
    pitfall #64). The gap between two blocks in this stack is always the
    **earlier** block's `margin-block-end`, so a heading's 40px belongs on
    the block wrapper, never as an `mb-10` on its own `h2` — that would
    sum with the loop's gap to 136px. A `heading` inside a `SectionBlock`
    keeps that panel's `space-y-8` (32px) instead: `section_block.html`
    wraps its children in no `data-block-type` element, so there is
    nothing for these rules to select.
40. **`RawHTMLBlock.clean()` validates tag balance only** (a hand-written
    stack-based `HTMLParser` subclass), not HTML safety or full
    conformance — catches the common stray/missing closing tag, nothing
    more. Doesn't descend into `<script>`/`<style>` as tags, so inline JS
    with `<`/`>` doesn't false-positive.
41. **Grid row-layout helpers** (`wtrx/blocks/__init__.py`) avoid a lone
    trailing item of 1: `_full_rows_with_balanced_tail()` (used by
    `CardGridBlock`, `ImageGridBlock`, `PersonCardGridBlock`) fills rows to
    the cap except the last, balancing across two rows only when the
    remainder is exactly 1; `_full_rows_merging_lone_remainder()` (used
    only by `LogoGridBlock`) instead folds a lone remainder into the last
    row (`max_per_row + 1`) — deliberately different because dense logo
    marks tolerate a fuller row better than cards do.
    `_balanced_rows()` is the older even-spread sibling both build on, and
    is still used directly by `ButtonGroupBlock`. Each block sets its own
    `MAX_PER_ROW` class attribute (3/3/4/5). Rows render as flex rows
    (`justify-center`, not CSS Grid, so a partial trailing row centers for
    free); card-shaped children need `h-full` on their own root, one level
    inside the flex item, to match sibling heights. **Both helpers convert
    their input with `list(items)` before slicing** — real Wagtail
    `ListValue` only supports integer indexing, and slicing it directly
    returns a bare list with no `.value`, failing deep inside Wagtail with
    a confusing `AttributeError`.
42. **New blocks with no real content yet use a hand-authored
    `Meta.preview_value`**, not `ContentPreviewMixin` — the mixin's
    `is_previewable` only goes `True` once a real published page has been
    harvested. Don't name a throwaway preview-function loop variable `_` —
    it's this file's `gettext_lazy` import and shadowing it breaks every
    `_("...")` call for the rest of that function.
43. **Condensing a block's separate heading field into its richtext body
    needs a hand-authored data migration keyed on the OLD field name per
    block type** — walk raw StreamField JSON like
    `0040_unify_block_background_values` does (revisions hold their own
    copy). The source richtext field is named differently across blocks
    (`text` on `ImageTextBlock`/`FeaturePanelBlock`, `content` on
    `CalloutBlock`/`CardCarouselBlock`) — a migration assuming one name
    uniformly silently discards the other blocks' real body copy under an
    orphaned key with no error. A block registered under more than one
    `StreamBlock` (e.g. `SignupActionKitBlock` is `signup_actionkit` in the
    body but `signup` inside `HeroCTABlock`) needs both type-strings
    mapped, or one registration's data is silently skipped. Re-harvest
    block previews after migrating real content.
44. **A `ListBlock`'s raw JSON wraps each item** as
    `{"id", "type": "item", "value": {...}}` — a migration walker written
    for `StreamBlock`-shaped entries (`{"type", "value"}`) silently no-ops
    on `ListBlock` items (`cards` on `CardGridBlock` etc.) unless it
    unwraps `item["value"]` first. This looks identical to "nothing to
    migrate" from the outside (no error, green tests) — always read a real
    migrated row's raw JSON to confirm, not just that `migrate` exits zero.
45. **A block mounted in more than one place can need two separate classes
    sharing a mixin, not subclass-adds-a-field** — Wagtail's declarative
    block metaclass sorts a struct's admin-form fields by creation order
    *across the whole module*, not MRO position, so a field added only in
    a subclass sorts to the end of its form instead of where intended.
    `SignupActionKitBlock`/`HeroSignupActionKitBlock` both redeclare their
    full field list and share only non-field logic via
    `SignupActionKitFormMixin`.
46. **Gating a block type from the picker can also break editing of
    already-placed instances.** The gated `groupedChildBlockDefs` Python
    return value feeds *two* JS consumers, not one: the "Add block" picker
    *and* the `StreamBlockDefinition` constructor's `childBlockDefsByName`
    lookup, which existing-instance hydration uses. Filtering it in Python
    alone breaks hydration of already-placed gated blocks (silently
    truncates the stream, and the next save persists the truncation).
    Fixed via `GatedStreamBlockAdapter` (`wtrx/blocks/__init__.py`) sending
    JS the **full** ungated defs plus a separate hidden-names list, and
    `gated-stream-block.js` building on the full list first, then filtering
    only `groupedChildBlockDefs` afterward. General lesson: before trusting
    "filtering X only affects Y" from a Python/Wagtail docstring, check how
    the compiled admin JS bundle actually consumes that same value.
47. **`CustomImage.description` is required** (`blank=False`, tightens the
    Images admin form only — not `.save()`, so programmatic imports still
    work blank). Feeds `default_alt_text` (#35). Legacy blank descriptions
    need `python manage.py backfill_image_descriptions [--apply]`, which
    reuses wagtail-ai's own generation path and caches results to avoid
    repeat LLM spend. The bulk multi-image uploader's "success" thumbnail
    state before the Title/Description form is submitted is stock Wagtail
    behavior (a staged `UploadedFile`, not yet a real row) — not a bug.
48. **Third-party scraped video/image imports need extra care**: an
    importer fetching third-party media (see `import_350_our_impact.py`)
    should verify `Content-Type` before trusting a URL that merely *looks*
    like a media file — an HTML player-bootstrap page can 200 with a
    `.mp4`-shaped URL. Widen-hosted video needs its real signed CDN URL
    extracted from the player page's own bootstrap JSON. Dedup-by-title
    lookups trust an existing row unconditionally — recovering from a bad
    import means deleting the affected rows first, not re-running.
    In-page anchor links (`#year-2021`) need rewriting to match the
    destination block's actual `id` scheme.
49. **Composing media-optional accordion/timeline content should use a
    small child `StreamBlock`** (`text`/`image`/`video` choices), not a
    richtext field plus "optional" bolted-on image/video StructBlock
    fields — `StructBlock.clean()` always validates every child
    regardless of whether the outer field marks it `required=False`, so a
    genuinely-blank optional image/video fails validation anyway. Letting
    absence be "no such block in the list" instead of "a blank struct"
    avoids the problem entirely. This is a real (non-additive) schema
    change requiring a data migration for any existing content using the
    old shape, plus a preview re-harvest.
50. **`SectionContentBlock`-style nesting excludes itself one level down**
    to prevent infinite StreamBlock nesting (e.g. `TimelineBlock` is only
    registered on `BodyStreamBlock`, not on `SectionContentBlock`/its own
    year-content block) — and also avoids class-definition-order cycles
    when a new block's content type depends on `SectionContentBlock`
    already being defined.
51. **Usercentrics is an integration now, but not a `head_html_field` one —
    it needs its own accessor.** `wtrx/integrations/usercentrics.py`
    registers it like any other integration (config `StructBlock`, added to
    `IntegrationsStreamBlock` in `site_settings.py`), so settings ID, script
    version, and the two service-ID lists (`reload_on_opt_in_service_ids`,
    `deactivate_blocking_service_ids`, both comma-separated and split
    client-side in the template) are all editable from Settings >
    Integrations with no deploy — that was the whole point of moving it off
    `WTRX_USERCENTRICS_SETTINGS_ID`/`_VERSION`/`_COUNTRY` env vars. But
    unlike Fundraise Up, it does **not** set `head_html_field`:
    `IntegrationSettings.head_html()` concatenates every integration's
    fragment at the very END of `<head>` (correct for a vendor script like
    Fundraise Up's), while Usercentrics' Consent Mode v2 `gtag('consent',
    'default', ...)` call must run before anything else that could set
    analytics/ad cookies — i.e. first in `<head>`, before the `<title>` even.
    `usercentrics_head.html` instead calls
    `IntegrationSettings.get_usercentrics_config()` (a plain wrapper around
    `get_integration_config("usercentrics")`) directly and renders itself
    first, same position it always occupied.
    - **`WTRX_USERCENTRICS_DISABLED` is the one env var that survived the
      move** — a hard local-dev kill switch (`dev.py` sets it `True`),
      independent of whatever `Settings > Integrations` says. Without it, a
      locally-imported production database dump (which carries a real,
      enabled Usercentrics entry) would load the external CDN script during
      local development, exactly the thing the old
      `WTRX_USERCENTRICS_SETTINGS_ID = ""` override in `dev.py` existed to
      prevent. `wtrx.context_processors.usercentrics` now only exposes this
      one flag; everything else comes from `settings.wtrx.IntegrationSettings`
      directly in the template.
    - **Migration `0071_seed_usercentrics_integration.py` seeds one
      "usercentrics" entry per existing `IntegrationSettings` row**, with the
      exact values that used to be hardcoded (settings ID
      `AelB3mtRNvAY5D`, script version `1.1.4`, the two service-ID lists).
      This is not optional bookkeeping: without it, deploying this change
      would silently turn off the consent banner in production the instant
      the migration runs — `get_usercentrics_config()` would find no entry
      until an editor manually added one — which is a compliance regression,
      not a cosmetic one. Idempotent (skips a site that already has an entry,
      same pattern as `0058_default_content_feedback_prompt.py`), and
      deliberately not reversible for the same reason that one isn't: no way
      to tell a seeded entry from one an editor has since hand-edited.
      Numbered `0070`/`0071`, not `0060`/`0061` as first generated — this
      work was rebased onto a branch that had independently claimed those
      same numbers for its own unrelated migrations. After a rebase like
      that, delete the renumbered-in-place files and re-run
      `makemigrations` rather than hand-editing the old ones: the
      `AlterField`'s `block_lookup` has to reflect the post-rebase model
      state (every block added on *both* branches), not just get a new
      filename and `dependencies` entry.
    - The service-ID fields stay plain comma-separated `CharBlock`s (not
      structured sub-fields) so the JS just does
      `'{{ uc.field|escapejs }}'.split(',').map(s => s.trim()).filter(Boolean)`
      client-side — the same "flat string, parsed at render time" pattern
      `FundraiseUpConfigBlock.eu_country_codes` already established, chosen
      over adding a nested `ListBlock` for one or two IDs at a time.
    - `manual_country_override` (QA/local testing, skips the `/cdn-cgi/trace`
      fetch entirely) is preserved as an optional field even though the
      config the settings ID/service-IDs were migrated from didn't need it
      populated — leaving it blank reproduces that exact behavior, so this
      is feature parity with the pre-migration override mechanism, not new
      surface area.
52. **`IntegrationSettings.custom_body_html` renders separately from
    `body_html()`**, right before `</body>` closes in `base.html` — unlike
    every per-integration `body_html_field` fragment (e.g. GTM's
    `<noscript>` fallback), which stays at the top of `<body>` because
    that integration specifically needs to run that early. Don't fold
    `custom_body_html` back into `body_html()`'s concatenation; it has no
    early-body requirement of its own.
53. **`request.is_preview` gates all integration head/body markup**
    (`IntegrationSettings.head_html()`/`body_html()`/`custom_body_html`) in
    `base.html` — Wagtail's live-preview iframe renders the real page
    template (`Page.serve_preview()`/`make_preview_request()` set
    `request.is_preview = True`; `Page.serve()` sets it `False`), so
    without the guard, analytics/tracking/vendor scripts would fire on
    every preview refresh of unpublished draft content. Block-embedded
    integrations (ActionKit forms, Fundraise Up, etc.) still render/fire in
    live preview — only the settings-level head/body injection is gated.

54. **A nested `StructBlock` field with `Meta.collapsed = True` is how to
    give a block a collapsed "Advanced settings" fieldset** — no custom JS,
    no per-panel classnames; Wagtail's block-editor `StructBlockAdapter`
    already reads `block.meta.collapsed` (`js_args()` in Wagtail's own
    `struct_block.py`) and renders that sub-block's fieldset closed by
    default, same expand/collapse chevron every other nested block gets.
    `DonateFundraiseUpBlock.advanced_settings`
    (`FundraiseUpAdvancedSettingsBlock`, `wtrx/blocks/__init__.py`) is the
    first user of this: it reverses the earlier "no per-block override, a
    deliberate product decision" stance on Fundraise Up region IDs (see the
    Fundraise Up geolocation pitfall history in
    `wtrx/integrations/fundraiseup.py`'s own docstring) — every field is
    optional and falls through to `FundraiseUpConfigBlock`'s site-wide
    value of the same name when blank, so an editor who never opens the
    section gets identical behavior to before this existed.
    - **Per-field fallback, not per-section fallback.** Each region
      resolves independently: `block_val(field) or site_val(field) or
      default_id`, where `default_id` is itself `block's own
      element_id_default or site's element_id_default`. Filling in only
      `element_id_us` in Advanced settings overrides just the US region for
      that one block instance; every other region still comes from the
      site config. This mirrors the site-wide config's own existing
      per-region-falls-back-to-default pattern one level up, rather than
      inventing a different resolution rule for the block-level override.
    - Reuses `FundraiseUpConfigBlock`'s exact field names and labels
      (`element_id_us`/`element_id_nl`/`element_id_ca`/`element_id_gb`/
      `eu_country_codes`/`element_id_eu`/`element_id_default`) rather than
      subclassing or importing that block directly — `FundraiseUpConfigBlock`
      also carries `enabled`/`installation_code`, which make no sense on a
      per-block override, and StructBlock composition (embedding one
      StructBlock's fields inside another) isn't how Wagtail block
      inheritance works; matching names/labels by hand is the actual
      established pattern here (same as `IMAGE_ALIGNMENT_CHOICES`/
      `BACKGROUND_COLOR_CHOICES` being shared constants rather than shared
      block classes).
    - `get_context()` still gates the *entire* region map (including any
      block-level override) on `fundraiseup_config` existing and being
      enabled — an override with the integration disabled would produce a
      Form ID pointing at a script that was never loaded in `<head>`, the
      same dead-button failure mode the original no-config case already
      guards against.
    - `ContentPreviewMixin`'s harvested-JSON previews (pitfall #31/#45)
      don't need updating for a new optional field like this: a harvested
      value with no `advanced_settings` key revives via `to_python()` into
      that sub-block's own defaults (every field blank), the same as if an
      editor had never opened the section — no re-harvest, no `KeyError`,
      unlike adding a *required* field would risk.
55. **A missing post image falls back to `Blogs.default_card_image`/
    `default_hero_image`, both set per-index-page rather than site-wide.**
    `Post._own_or_body_image()` (`wtrx/models.py`) is the shared first two
    steps for both — this post's own `hero_image`, else the first image
    found in the body — factored out because its two callers,
    `get_card_image()` and `get_hero_image()`, differ only in which of the
    parent `Blogs` page's two FKs they fall back to next.
    `get_card_image()` falls back to `default_card_image`, used everywhere a
    post is shown as a card (`Blogs.get_context()`, the related-posts loop,
    `PageCardsBlock`). `get_hero_image()` falls back to `default_hero_image`
    for this post's own header (`Post.get_context()` overrides
    `ctx["hero"]["image"]` with `self.get_hero_image(parent=parent)` after
    building the banner hero context) — and, when that field is left blank,
    chains one step further to `default_card_image` too, so a `Blogs` page
    that only ever configured the (older) card field keeps its posts'
    headers filled exactly as before `default_hero_image` existed. A card
    never falls back to `default_hero_image` — that chaining is one-way.
    - **Deliberately scoped per-`Blogs`-page, not a site-wide setting**
      (e.g. on `BrandingSEOSettings`, next to `default_meta_image`): a
      "BREAKING NEWS" graphic is right for a Press Releases index (where a
      statement often has no photo) and wrong as a fallback on ordinary
      blog posts, which almost always have a real photo and shouldn't
      silently get a press-release-branded image if an editor forgets one.
      A site can still set either field on more than one `Blogs` page, or
      leave both blank anywhere they don't apply — same "settings over
      hardcoding" reasoning as the Integrations framework (rule #8), just
      scoped to a page instance instead of a site setting.
    - **Two separate fields, not one reused for both roles, because the
      right image for each role can genuinely differ** — e.g. a wide banner
      graphic across the top of a press release's own page versus a small
      square icon on its card in a listing. Most sites will only ever set
      `default_card_image`; `default_hero_image` exists purely as an
      override for the (presumably rarer) case where that same image looks
      wrong stretched across a full-bleed header.
    - `get_card_image(self, parent=None)`/`get_hero_image(self, parent=None)`
      both take an optional parent to avoid a redundant `get_parent()` query
      at call sites that already have the post's parent `Blogs`/index page
      on hand (`Blogs.get_context()` passes `self`; `Post.get_context()`'s
      related posts loop and `PageCardsBlock.get_context()` pass their own
      already-resolved parent/`specific_index`) — each resolves its own via
      `self.get_parent().specific` only when omitted. Any future caller
      should pass `parent=` if it already has the parent page in scope,
      rather than accepting the extra query.
    - There is still no `is_press_release` flag or coupling to
      `AdminMenuSettings.press_releases_index_page` anywhere — "is this a
      press release" is still purely which `Blogs` page a `Post` happens to
      live under (see `Blogs.post_label`'s docstring), and this feature
      doesn't change that. Setting `default_card_image`/`default_hero_image`
      on the Press Releases page is what makes it press-release-specific in
      practice, not any code-level type check.
56. **350.org's other-language "country sites" (e.g. `https://350.org/fr`)
    are separate WordPress multisite subdirectory installs**, not a
    `?lang=` query param on the main site — confirmed live:
    `https://350.org/fr/wp-json/` returns its own independent site index
    ("350 Français"), and `/fr/sitemap_index.xml`,
    `/fr/press-release-sitemap.xml`, `/fr/wp-json/wp/v2/posts` all exist in
    the exact same shape as the main site's, served by the same theme (a
    live `/fr/` press release page has the identical
    `#press-release-header`/`#post-time`/`article.clearfix` markup
    `fetch_press_release()` already expects). So `import_350_blog.py`/
    `import_350_press_releases.py`'s `--site` option
    (`resolve_site_base_url()`/`verify_site_reachable()` in
    `_wp_content_utils.py`) only ever needs to swap the base URL — Yoast
    site-name stripping, author-byline scraping, and image URLs are all
    already relative to whatever page/response was actually fetched, so
    none of that needed changing.
    - **Deliberate scope decision**: imported country-site content lands
      as an ordinary `Post` under whichever `--target` `Blogs` page an
      editor has created for it, in the existing single (English) Wagtail
      locale — not a new Wagtail Locale/translation tree. `WAGTAIL_I18N_ENABLED`
      is already `True` and `wtrx/templates/wtrx/components/language_switcher.html`
      is already wired into the header expecting more entries in
      `WAGTAIL_CONTENT_LANGUAGES` (currently English-only, with a comment
      inviting forks to add more) — that's the more "correct" long-term
      path for native `/fr/...` URLs and a working language switcher, but
      it needs a locale enabled in settings and a translated/independent
      page tree built in the admin, which is real setup cost beyond an
      import script. Revisit only if a site actually wants that.
    - `CATEGORY_SLUG_MAP`/`TITLE_CATEGORY_KEYWORDS` (`import_350_blog.py`)
      are English-only, so a non-English import ends up with zero
      categories — the same "no guessed category" fallback that already
      applies to any English post matching neither source, not a bug
      specific to `--site`.
57. **A raw boto3 `put_object()`/`copy_object()` call bypasses
    `STORAGES["default"]["OPTIONS"]["object_parameters"]` entirely** — that
    dict (currently just `CacheControl`, a 7-day max-age; see
    `production.py`) is applied by django-storages' `S3Storage.save()` on
    every *normal* upload through Wagtail, not by S3 itself, so any code
    path that writes objects directly against the S3 API instead needs to
    set it by hand or the object lands with no `Cache-Control` header at
    all. `wtrx/management/commands/migrate_media_bucket.py` (a one-off,
    since removed — see git history) did exactly this while moving media
    into Divio's Object Storage bucket, and every object it copied is
    missing the header as a result — confirmed live via a PageSpeed
    Insights "Use efficient cache lifetimes" audit flagging the site's
    `s3.amazonaws.com`-origin media (6.3 of 6.4 MiB total estimated
    savings). `wtrx/management/commands/backfill_media_cache_control.py`
    (a one-off, since removed — see git history) fixed existing objects in
    place via S3's server-side `CopyObject` (`MetadataDirective=REPLACE`,
    same bucket/key — no bytes re-transferred through that process), reading
    `CacheControl` from `default_storage.get_object_parameters()` rather
    than hardcoding it a second time, so it couldn't drift from
    `production.py`. `REPLACE` wipes *all* metadata not explicitly passed
    back — the command read the object's own `ContentType`/
    `ContentDisposition`/`ContentEncoding`/`ContentLanguage`/`Metadata` via
    `HeadObject` first and carried them through unchanged; omitting
    `ContentType` in particular would have silently reset every re-copied
    object to `binary/octet-stream`. It reused `default_storage.connection`'s
    own boto3 client rather than constructing one by hand, so
    `endpoint_url`/`region`/`addressing_style` couldn't drift from whatever
    environment it ran in (this project's bucket names can contain a literal
    dot — see the S3 config comments in `production.py` — which breaks
    hand-rolled client config that gets `addressing_style` wrong). If this
    recurs (e.g. a future bulk-copy tool repeats the same mistake), that
    removed command's approach is the reference implementation to redo.
58. **`wagtailmedia.models.Media.thumbnail` is a plain `FileField`, not a
    Wagtail `Image` FK** — Wagtail's rendition pipeline (resize, format
    conversion, caching) never touches it, so whatever an editor uploads as
    a video's poster frame is served completely as-is. It's used in exactly
    one role site-wide, as a `<video poster="...">` (hero's background
    video, `video_block.html`, `accordion_block.html`) — confirmed live via
    a PageSpeed Insights "Improve image delivery" flag on an 831 KiB raw PNG
    hero-video thumbnail (a design-tool export judging by its filename,
    "Rectangle_130.png") served completely unresized. `wtrx/models.py`'s own
    help text tells editors to upload one for exactly this poster-frame
    role, so this was a data-quality gap in a deliberately-used feature, not
    a bug in the poster fallback chain itself (rule #4 above).
    `wtrx/media_optimization.py` hooks `pre_save` on `wagtailmedia.Media` (a
    plain Django signal, connected in `WtrxConfig.ready()` — Media isn't a
    swappable/subclassable model in this project the way `CustomImage` is
    for Wagtail's own Image, so a signal is the only hook point available)
    to cap every new thumbnail to `MAX_THUMBNAIL_DIMENSION` and re-encode it
    as JPEG before it reaches storage — a video poster always renders opaque
    underneath the `<video>` element, so PNG's lossless/alpha features are
    wasted bytes regardless of the source format; transparency is flattened
    onto white rather than naively dropped (which would otherwise reveal
    garbage/black in the RGB channels beneath transparent pixels).
    `backfill_video_thumbnails` applies the same processing to existing
    `Media` rows. Uses plain Pillow rather than Willow (Wagtail's own image
    library, used by `CustomImage`/`CustomRendition`) — Willow's newer
    plugin-registry API (operations resolved dynamically per backend) makes
    a one-off "resize down, re-encode as JPEG" task on a raw `FileField`
    more awkward than reaching for Pillow directly, which Willow itself
    sits on top of anyway. The signal skips reprocessing when a save doesn't
    touch `thumbnail` at all (compares the instance's value against the
    database's), so editing a `Media` item's title doesn't recompress its
    thumbnail every time — the backfill command, which intentionally
    reprocesses every row regardless, disconnects the same signal for the
    duration of its run (reconnected in a `finally` block) since its own
    `Media.save()` call would otherwise trip that same hook a second,
    redundant time (the optimized filename never matches the database's
    original one, so the "already processed?" check can't short-circuit it
    the way it does for an editor's unrelated save).
59. **A PNG or JPEG source keeps generating a rendition in that same format
    for any filter spec that doesn't request one explicitly** (e.g.
    `fill-640x360`) — Wagtail's own `default_conversions` dict
    (`wagtail/images/models.py`) converts avif/bmp/webp sources (and
    unanimated GIF) to PNG, but has no entry for PNG or JPEG themselves, so
    both fall through unchanged. Confirmed live via a PageSpeed Insights
    "Improve image delivery" flag: an in-body screenshot's `fill-640x360`
    rendition was a 168 KiB PNG the same source now produces as ~40 KiB in
    WebP; JPEG was added to the same setting after the PNG-only version
    shipped and the same report kept flagging JPEG-sourced images for an
    identical reason.
    `WAGTAILIMAGES_FORMAT_CONVERSIONS = {"png": "webp", "jpeg": "webp"}`
    (`settings/base.py`) fixes this project-wide with no template changes —
    WebP (not JPEG) as PNG's target so a PNG with real transparency still
    renders correctly instead of being flattened onto a white background
    (Wagtail's own JPEG-output path does exactly that via
    `willow.set_background_color_rgb`); JPEG sources re-encode to WebP too
    even though that's a second lossy pass on an already-lossy source —
    WebP's better compression still nets a real size win for photographic
    content in practice, and nothing in this project depends on a JPEG
    rendition's exact bytes surviving untouched. Two call sites
    in `base.html` are deliberately pinned away from this default with an
    explicit `format-jpeg`/`format-png` filter-spec token (**not** a dotted
    suffix on the size token — `fill-1200x630.jpg` raises
    `InvalidFilterSpecError` since `FillOperation.construct()` does a bare
    `width, height = size.split("x")`; the correct form is a second
    space-separated spec, `fill-1200x630 format-jpeg`, joined into one
    pipe-separated `Filter.spec` by the `{% image %}` tag parser) since
    their consumer isn't a browser rendering our own page:
    `og:image`/`twitter:image` (social link-preview crawlers have
    historically inconsistent WebP support — a broken share preview is a
    far more visible regression than the bandwidth saved on one image) and
    the favicon (needs the broadest possible browser/OS support, and is
    small enough that WebP's savings there are negligible anyway).
    Changing this setting does **not** retroactively touch already-generated
    renditions — Wagtail caches them per `(image, filter_spec)` in the
    `Rendition` table/storage regardless of this setting, so the fix only
    reaches new renditions until `python manage.py
    wagtail_update_image_renditions` (Wagtail's own built-in command; no
    project-specific backfill needed here) regenerates the existing ones.
60. **An oversized source image can OOM-kill a live worker on its first
    render, with nothing in the logs.** Wagtail's rendition pipeline always
    fully decodes the source image into memory before resizing it down, for
    *any* filter spec, regardless of the requested output size — a
    `fill-640x360` card thumbnail still pays the cost of decoding the whole
    original first. Confirmed live: `import_350_blog.py` imported a
    WordPress "full size" upload URL (see `_full_size_wp_image_url()`) that
    turned out to be a raw, uncompressed-for-web 8192x5464 (44.8MP)
    original; the first visitor to a blog listing page containing that
    post's card triggered the decode, which exceeded the container's
    memory and got `SIGKILL`'d by the OOM killer. `SIGKILL` can't be
    caught or handled by anything — not gunicorn, not Python's exception
    machinery — so **nothing gets written to any log**, app or otherwise;
    the only visible symptom was Cloudflare's generic 502 page (the origin
    never responded at all) and, if you know to look, a container-restart
    event in Divio's own infra-level Events panel rather than its app log
    stream. A worker *timeout* (as opposed to OOM) usually does leave a
    `WORKER TIMEOUT` line — no log lines at all points at OOM specifically.
    To diagnose without risking more crashes: pull the suspect page's
    posts/images via `Blogs.get_listing_queryset()` and check each image's
    already-stored `width`/`height` (a plain DB read, no re-decode) for an
    outlier — no need to actually attempt the render to find the culprit.
    Fixed at the source: `_wp_content_utils.downsize_oversized_image()`
    caps every imported image to `MAX_IMPORTED_IMAGE_DIMENSION` (3000px on
    the longest side) at import time, inside `download_image()`'s existing
    broad `except` (so a resize failure is reported the same way a bad
    decode already was, rather than needing its own special case). Unlike
    `wtrx/media_optimization.py`'s video-thumbnail handling (which always
    re-encodes to JPEG, since a thumbnail only ever plays one fixed poster
    role), this preserves the original format/mode — these become real
    content images (hero, cards, in-body) used at a range of sizes, so
    transparency and format still matter. Deliberately scoped to the
    import pipeline only, not a blanket signal on every `CustomImage` save
    the way media thumbnails get one — an editor's own high-res upload for
    a full-bleed hero is a legitimate, intentional choice, not an untrusted
    third-party fetch. `backfill_oversized_images` (mirroring
    `backfill_video_thumbnails`) is the one-time fix for images imported
    before this existed; it deletes the image's existing renditions after
    replacing its file, since they were generated from the old oversized
    original.
61. **`SignupActionKitBlock`'s two third-party scripts are render-blocking
    by default, but only one of them can safely be un-blocked.** Confirmed
    live via PageSpeed Insights flagging both on `wagtail.350.org`: jQuery
    from `ajax.googleapis.com` (loaded by `_actionkit_form.html` for
    `actionkit.js`'s benefit) used `document.write()`; and
    `https://www.google.com/recaptcha/api.js` arrives already embedded, with
    no `async`, *inside* ActionKit's own fetched form fragment (see
    `fetch_embed_form_html`), so there's no template tag to attribute in the
    first place — it's third-party HTML spliced in via
    `{{ form_html|safe }}`, the same class of problem as pitfall #36's
    Tailwind-class leak.

    reCAPTCHA's fix stands: `_make_recaptcha_async()` in
    `wtrx/integrations/actionkit.py`, a regex substitution run on the
    fragment right after fetch (before caching), adds `async` to recaptcha's
    own script tag — safe because recaptcha auto-scans the DOM for
    `.g-recaptcha` elements once *it* has loaded, on its own schedule; it
    never needs to run at a specific point in the parse.

    **jQuery's `document.write()` must stay, and was reverted after actually
    breaking production.** The instinct is the same fix — replace it with a
    dynamically created, `appendChild`-ed `<script>` (async by default per
    the HTML spec) — and that was shipped once. It's wrong here specifically
    because `form_html` isn't just form fields: ActionKit's own fetched
    fragment carries several inline `<script>` blocks (e.g.
    `jQuery( document ).ready(function() {...});` near the very top, for its
    "oneclick" lead-prefill, plus more further down for radio/checkbox
    styling) that call jQuery *immediately and synchronously* as the parser
    reaches them, with no deferral of their own. `document.write()`'s
    parser-pausing behavior is what guarantees jQuery has finished loading
    and executing before the parser gets there — confirmed live via
    `Uncaught ReferenceError: jQuery is not defined` in production once the
    async version shipped (intermittent — a race against fetch time, so
    worse on mobile/slow connections, which is exactly why it wasn't caught
    immediately). Signup submission itself was never at risk — validation/
    submit further down this same file is vanilla JS, not jQuery-dependent
    — but the oneclick lead-hiding and radio/checkbox styling silently
    no-op every time the race is lost. There's no way to keep those two
    ActionKit-fragment features reliable without the synchronous guarantee,
    so this one specific "render-blocking requests" flag from PageSpeed is
    not fixable from our side short of ActionKit dropping jQuery from its
    own fragment. Don't re-attempt the dynamic-`<script>` version without
    changing that.

    Either way, a jQuery-loading `<script>` block that literally mentions
    `ajax.googleapis.com` must stay wrapped in Django's
    `{% if not is_block_preview %}` (not just an inner JS `return;`) or the
    literal string leaks into block-picker preview HTML and breaks
    `test_previews_never_call_a_third_party_platform`, which asserts on the
    literal string, not on whether the JS actually runs.

## Git Conventions

- Branch from `main`. Descriptive names: `feature/signup-block`,
  `fix/hero-image-fallback`.
- Imperative-mood commit messages: "Add CardGridBlock..." not "Added...".
- Never commit `node_modules/` or `static_compiled/` (gitignored).

## Documentation Maintenance

Keep these in sync with the repo, updated in the same commit as the change
they describe:

- **`PLAN.md`** — tech stack, file structure, phase status
  (`✅ COMPLETE`/`🔄 IN PROGRESS`/checkboxes for in-progress items).
- **`AGENTS.md`** — this file: build commands, pitfalls, architecture rules.
- **`README.md`** — commands, stack description, project structure.

## Context Management

Applies to any session in this repo, not just design/style work:

- Compact proactively once a session has done several rounds of
  investigation-and-fix — don't wait for automatic summarization.
- Fork exploratory/one-off investigation (e.g. "where does this render") to
  a subagent instead of keeping its raw output in the main conversation.
- Don't re-read a screenshot once you've reported what it showed — trust
  your own prior summary.

## Code Review Requirement

Present changes to the user and explicitly ask them to review; wait for
sign-off before committing. There is no mandatory automated agent-review
step — `/code-review` (or similar) is available on request, not a required
gate.

60. **There is one container string for full-width content:
    `mx-auto max-w-[1500px] px-4` — a flat 16px gutter at every
    breakpoint.** Used by `components/hero.html` (both variants),
    `section_block.html`, `image_block.html`, `quote_block.html`,
    `timeline_block.html`, `signup_actionkit_block.html`,
    `feature_panel_block.html` and `donate_fundraiseup_block.html`. Two
    things used to break alignment here and both are easy to reintroduce:
    - **The two idioms are not equivalent.** `max-w-[1500px] px-8` on one
      element (cap and gutter together) gives a 1436px panel; a `w-full
      px-8` shell wrapping a `max-w-[1500px]` child gives a 1500px panel
      whose edge sits 32px further out. `SignupActionKitBlock`,
      `FeaturePanelBlock` and `DonateFundraiseUpBlock` were all the second
      shape and so sat wider than `SectionBlock` despite three of them
      naming 1500px. Put the cap and the gutter on the *same* element.
    - **`px-4 sm:px-6 lg:px-8` is not the full-width gutter.** It is the
      *body column's* gutter, and it is still correct there and on the
      narrower `max-w-[1218px]` card families. A full-width block that
      copies it is inset 8–16px too far from `sm:` up.
    The nav (`header.html`) deliberately keeps `px-4 sm:px-6 lg:px-8`, so
    its content is inset further than the hero directly beneath it at
    `sm:` and above. That is the long-standing behaviour (the page hero
    always had a flat `px-4`), not an oversight — changing it is a
    one-line edit if the design ever wants them flush.
    `card_carousel_block.html` is the other deliberate exception: it uses
    `pl-4 sm:pl-6 lg:pl-8`, a left gutter only, because the carousel is
    meant to bleed off the right edge.

61. **The gap between the hero and the first body block is conditional,
    and lives entirely in CSS.** `base.html` gives `<main>` a flat
    `my-32` (128px). An unlayered rule in `main.css` ("Hero -> first
    full-bleed block") overrides `margin-block-start` to 16px, but only
    when **both** hold: `body:has(.wtr-page-hero)`
    (set by `hero.html` only when `in_body` is false, so a mid-body
    `HeroBlock` never triggers it and a `hide_hero` page correctly keeps
    128px) **and** the stack's `:first-child` is one of exactly four
    panel-shaped types: `section`, `signup_actionkit`,
    `donate_fundraiseup`, `feature_panel`. Those four render as filled
    rounded panels at the hero's own width, so hero-then-panel reads as
    one stack. Every other type keeps 128px — **including full-bleed ones
    like `image`, `quote` or `card_grid`**, which sit directly on the page
    background and need the section break. "Is full-bleed" and "is a
    panel" are different questions that merely overlap; the four are
    listed by hand and a new panel block must be added to that selector
    deliberately.
    **That margin is the only source of the gap below a hero.** The hero
    wrapper in `components/hero.html` used to carry a `pb-4` of its own as
    well, which summed with this rule to a visible 32px wherever it fired
    (and gave a mid-body `HeroBlock` a stray 16px under it that no other
    block in the stack has). Both hero variants now end flush at their
    panel edge — don't reintroduce vertical padding there to "fix" a gap;
    change this margin instead.

62. **`wtr-btn` sets `white-space: nowrap`**, so a button cannot wrap
    however wide its container is. `ButtonGroupBlock`'s "vertical" layout
    caps its column (`mx-auto max-w-sm`) and stretches its buttons
    (`items-stretch` at every breakpoint, not just below `sm:` as before),
    which only reads correctly because `.wtr-button-group-vertical
    .wtr-btn` in `main.css` overrides `white-space` to `normal` and adds
    `text-align: center` — `wtr-btn` sets no text-align, so a stretched
    `inline-block` would left-align its label beside centred shorter
    siblings. Unlayered, so it beats `wtr-btn`'s own `@utility`
    declarations. `feature_panel_block.html` solves the same problem
    inline on a single button. Horizontal rows deliberately keep
    content-width, `nowrap` buttons — a row of stretched buttons reads as
    a segmented control rather than as separate CTAs.

63. **`ContentPage.hide_hero` is gated by `FieldPanel(permission=
    "wtrx.disable_hero")`**, a custom permission declared in
    `ContentPage.Meta.permissions` rather than on a proxy or unmanaged
    model — it is the only page type with the field, so there is nothing
    to share and it costs one `AlterModelOptions` instead of a second
    model and ContentType. Wagtail removes the field from the form
    entirely for users without it, so it cannot be set by POSTing either;
    superusers always pass `has_perm`. Assign it to a group in Settings >
    Groups.
    The checkbox lives **inside** the Hero `MultiFieldPanel`, as its last
    child — after the fields it turns off. That is why `HeroMixin` exposes
    `banner_hero_fields` (the panel's children) alongside
    `banner_hero_panels` (the assembled panel): `ContentPage` rebuilds the
    same panel around those children plus the toggle, since the shared
    `banner_hero_panels` can't carry a field `IndexPage` and `Blogs` lack.
    Sharing `FieldPanel` instances across two `MultiFieldPanel`s on two
    models is safe — `Panel.bind_to_model()` clones before setting
    `.model`. Nesting does not weaken the gate:
    `PanelGroup.get_form_options()` merges each child's `field_permissions`
    dict upward, so the field stays absent from the form itself. Note a
    nested `PanelGroup` renders via `multi_field_panel_child.html` (a bare
    `<h3>`, no toggle), so `classname="collapsed"` does nothing there — a
    collapsed fieldset needs a top-level panel, unlike blocks, which get
    one from `Meta.collapsed` (pitfall #54). The hero owns the page's only `<h1>` (via
    `hero.headline`, which falls back to the page title), so
    `content_page.html` emits `<h1 class="sr-only">{{ page.title }}</h1>`
    when the hero is hidden — without it the document has no `h1` at all,
    since every body heading is `h2` or lower.

64. **`HeadingBlock` and the card-row heading are kept in step by
    convention, not by shared code.** `heading_block.html` lifts its
    container tiers and its whole `h2` class string from
    `card_grid_block.html`'s own optional heading, so a standalone heading
    and a card-row heading on the same page line up on the same edge and
    share a type size. Nothing in code links them — changing one means
    changing the other by hand, in both templates.
    The one place they deliberately differ is where the 40px below the
    heading is applied: `card_grid_block.html` puts `mb-10` on its `h2`
    (an internal gap, down to its own cards), while `HeadingBlock` gets
    the same 40px from a `data-block-type='heading'` rule in `main.css`'s
    "Body-stack spacing" (a gap between two blocks, which in that stack is
    always the earlier block's `margin-block-end` — see pitfall #39).
    Putting `mb-10` on `heading_block.html`'s `h2` as well would sum with
    the page loop's `space-y-24/32` to 136px.
    It is also registered on both `BodyStreamBlock` and
    `SectionContentBlock`, and must stay in every page template's
    full-bleed block-type list — like the card families it owns a
    `max-w-[1218px]` tier that is unreachable inside the shared body
    column.
65. **The URL prefix is the language code, and `WAGTAIL_I18N_ENABLED` has to
    stay on.** Routing is `Page.route_for_request()` →
    `site.root_page.localized.route(...)`: the prefix in the URL sets the
    active language, which picks which root page (translation) serves the
    request. `Site.get_site_root_paths()` emits one root path per translation
    of the site root, all on the **same** Site — so languages need no extra
    `Site` row and no extra domain. A `Site` is matched by hostname+port only,
    never by path, which is why an extra domain is the *only* way to give a
    region its own root URL (and the only way to give it its own
    `BaseSiteSetting` row — branding, integrations and consent config are
    per-Site, shared across languages).
    An earlier design put regional sites *under* Home (`/brasil/`) with the
    flag off. It was rejected: with the flag off, translation tooling has to
    be rebuilt by hand, and with the flag on, `chooser.BrowseView.get()`
    filters pages to the parent's locale, which also backs
    `CopyForm.new_parent_page` — making "copy the English Home into the
    Brazilian section" impossible in the admin. 350.org's live sites already
    use `/fr/`, `/pt/`, `/de/`, `/id/`, and `/brasil` already redirects to
    `/pt`, so the native scheme matches the public URLs.
    Two behaviours worth knowing: `prefix_default_language=False` makes
    `LocaleMiddleware.process_request` force `LANGUAGE_CODE` on any unprefixed
    path, so a Portuguese browser hitting `/about/` gets **English**, with no
    auto-redirect (the redirect branch only runs when the default language is
    itself prefixed); and `Vary: Accept-Language` is added to unprefixed
    (English) responses only — prefixed ones escape it, so the Cloudflare
    cache fragments on English URLs, not `/pt/` ones.
66. **A CharBlock holding an identifier must be an `IdentifierBlock`**
    (`wtrx/blocks/__init__.py`). wagtail-localize extracts *every*
    `CharBlock`/`TextBlock`/`RichTextBlock` as a translatable segment, so
    without this an ActionKit `short_form_id`, an `anchor_id`/`anchor`, a
    Fundraise Up `designation_id`/`element_id_*` or a `TimelineYearBlock.year`
    is handed to a translator (or a machine) and comes back broken — a form
    that no longer resolves, an in-page link that no longer lands. The opt-out
    is wagtail-localize's own per-block pair, `get_translatable_segments()`
    (`segments/extract.py`) and `restore_translated_segments()`
    (`segments/ingest.py`), both checked before its type-based fallback.
    Switching a field to it is a block-definition change only — same storage,
    same admin widget, one auto-generated `AlterField` migration.
    `slug` **is** deliberately translatable (that is what produces
    `/pt/sobre-nos/`). `wtrx/tests/test_i18n.py` asserts the exclusions
    against the real extractor; add a case there when adding a new
    identifier field.
67. **Preview renders in the editor's language unless a page overrides it.**
    A served page gets its language from the URL prefix, but preview is
    requested from an admin URL *outside* `i18n_patterns`, and Wagtail's
    `Page.serve_preview()` never touches the active translation — so a
    Portuguese page previews with English chrome. `BasePage.serve_preview()`
    wraps `super()` in `translation.override(self.locale.language_code)` and
    forces the `TemplateResponse` to render **inside** that block, because a
    TemplateResponse renders lazily, after the context manager would have
    exited.
68. **Translation catalogues: `makemessages --all` only updates locales that
    already have a directory.** It globs `locale/*`, so a language added to
    `WAGTAIL_CONTENT_LANGUAGES` but never yet compiled is silently skipped —
    which is why `make messages` derives `--locale=` arguments from settings
    instead. Catalogues live in two places: `locale/` for `templates/` and
    `wagtail_wtr/`, and `wtrx/locale/` for the app (the project run ignores
    `wtrx` so each string lands in exactly one catalogue, and the app run
    needs `wtrx/locale/` to exist first). `compilemessages` must be given
    `--ignore=.venv`, or it walks into site-packages and recompiles every
    installed package's catalogues. `.po` is committed, `.mo` is gitignored
    build output compiled in the Dockerfile — which pins
    `DJANGO_SETTINGS_MODULE=wagtail_wtr.settings.base` so the build never
    depends on runtime secrets.
69. **The language switcher is links, not `set_language`.** The old
    `language_switcher.html` POSTed to Django's `set_language` with
    `next=request.path`, which switches the *interface* language and returns
    to the same path — in this architecture that path belongs to another
    language's tree and usually does not exist (translated slugs differ).
    `language_links` (`wtrx_tags.py`) resolves each language through the
    page's real translations, falling back to that language's home page, and
    omits a language with neither. `page_translation_alternates` is its
    stricter sibling for `<head>`: hreflang alternates are emitted only for
    genuinely linked pages (never the home-page fallback, which would claim
    two unrelated pages are the same content), plus `x-default` for the
    default language.

70. **"Add locale" in the admin does nothing when every configured language
    already has a row.** `LocaleForm` (`wagtail/locales/forms.py`) builds its
    `language_code` choices from `WAGTAIL_CONTENT_LANGUAGES` *minus* the
    languages that already have a `Locale`, so once `bootstrap_locales` has
    run there is nothing left to offer: the create view still returns 200, but
    with an empty dropdown, and the button reads as broken. Adding a language
    is therefore always two steps in this order — settings entry (a code
    change and a deploy), then the `Locale` row (`make locales`, or the admin).
    Deletion is one-way in practice: `Locale` FKs are `on_delete=PROTECT`, so a
    locale with pages cannot be removed.

71. **Two kinds of locale, and the difference decides the URL.** A *country
    variant* (`pt-br`, `fr-fr`, `de-de`, `id-id`) is a country site with its
    own content and navigation, served under its own name via
    `WTRX_LANGUAGE_URL_PREFIXES` (`/brasil/`, `/france/`). A *plain code*
    (`pt`, `fr`, `es`) exists for translating an individual global page and
    serves under the code (`/es/about/`). Keeping them apart is the whole
    point: with the Brasil site on plain `pt`, a Portuguese translation of a
    global page would land at `/brasil/about/`, inside the Brazilian site —
    the same way a French translation of `/canada/` lands under `/france/` if
    France holds plain `fr`. Splitting costs nothing in translation work: a
    country variant falls back to its base language's catalogue, so `pt-br`
    reads `locale/pt/` and needs no `.po` of its own. Retagging a country site
    from `pt` to `pt-br` changes no URLs (the prefix maps to the slug it
    already has), so `convert_section_to_locale <id> pt-br` reports `created 0
    redirects` — that zero is the signal it was a pure relabel.
    A plain locale with no content yet still answers at its prefix: `/pt/`
    returns 200 showing the **English** home, because `Page.localized` falls
    back to the source page when no translation is live. Not a bug, and the
    same reason an alias parent shows English (pitfall #69).

72. **A language tree's URL prefix is mapped, not its language code.**
    Django ties the prefix to the code, so French would serve at `/fr/` and
    there is no setting for it. `WTRX_LANGUAGE_URL_PREFIXES` maps a code to a
    segment instead (`fr` → `france`, `pt` → `brasil`), which is what lets the
    country sites keep the URLs they already have rather than moving to `/fr/`
    behind redirects. A language with no entry keeps its code (`/es/`), which
    suits one used for occasional translations rather than a whole site.
    `wtrx/i18n.py` holds both halves, and both are required: a
    `LocalePrefixPattern` subclass (what `reverse()` writes and what the
    resolver strips) **and** a `LocaleMiddleware` subclass (Django's
    `get_language_from_path()` matches the first segment against language
    codes, so `/france/` means nothing to it and the tree would serve in
    English or 404). Subclassing rather than reimplementing is load-bearing:
    `is_language_prefix_patterns_used()` finds i18n URLs by `isinstance`, and
    `LocaleMiddleware` reads its answer to decide whether to force the default
    language on an unprefixed path.
    A mapped language is reachable **only** at its prefix — `/pt/` 404s — so
    each tree has one canonical URL. Two consequences worth knowing: a mapped
    prefix shadows any top-level English page with the same slug, and the
    prefix is per *language*, so a Portuguese translation of a global page
    lands under `/brasil/` whether or not it is Brazilian. `LocalePrefixPattern`
    is not public Django API; `test_i18n.py` asserts resolving and reversing in
    both directions so an upgrade that changes it fails the suite, not the site.

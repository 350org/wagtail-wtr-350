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
   `hero` context dict with exactly these keys: `headline`, `copy`,
   `copy_is_block`, `image`, `video`, `link_text`, `link_page`, `link_url`,
   `in_body`, `minimal`. `in_body=True` only for `HeroBlock` — it swaps the
   page-hero's flat 16px gutter for the `px-4 sm:px-6 lg:px-8` every other
   full-bleed body block uses. `hero` and `quote` must stay in each page
   template's full-bleed block-type list (both own a `max-w-[1500px]`
   wrapper that's unreachable inside the shared body column). When
   `hero.video` is a wagtailmedia `Media`, the template switches to a
   two-column layout (text left, video right; stacked on mobile), hiding
   the background-image overlay. Poster fallback: wagtailmedia thumbnail →
   `hero.image` at `fill-1280x720` → none.
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
    renders as an inset rounded panel (`max-w-[1500px]
    px-4 sm:px-6 lg:px-8`, matching `image_block.html`'s and the nav's own
    container/radius) publishing `data-bg-tone` for children to invert
    against. `IMAGE_ALIGNMENT_CHOICES` is the same kind of shared constant
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
    600 (not 500), `font-semibold`/`font-bold` both = 700 (no utility
    reaches Heavy/800). **h1/h2 get Heavy, h3-h6 get Bold via bare element
    rules in `main.css`** (unlayered, so they beat any weight utility on a
    heading outright, including Tailwind Typography's own hardcoded prose
    weights) — putting a weight utility on a heading silently does
    nothing; add/change an unlayered element rule instead. Only `woff2`+
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
39. **Some block adjacencies auto-tighten to 32px** (from the page loop's
    default 96px/128px `space-y-*`) via unlayered `:has()` rules in
    `main.css`'s "Body-stack spacing" section — around `button` blocks, and
    `text` immediately before a card row. Deliberate and automatic, not
    editor-configurable, and one-directional (card-row → text stays at the
    full gap).
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

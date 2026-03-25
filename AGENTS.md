# AGENTS.md -- wagtail-wtr

Guidelines for AI coding agents working in this repository.

## Project Overview

wagtail-wtr is a Wagtail project template for campaign, nonprofit, and organizer
websites. It is used via `wagtail start --template` and contains a reusable `wtrx/`
sub-app inside `project_name/` designed for eventual extraction to a pip package.

See `PLAN.md` for the full specification and architectural decisions.

## Repository Structure

The repo root IS the template. `project_name/` is renamed by `wagtail start`.

- `project_name/wtrx/` -- Core reusable app. DO NOT put site-specific code here.
- `project_name/wtrx/blocks/` -- StreamField blocks, one file per category.
- `project_name/wtrx/site_settings.py` -- All Wagtail site settings models.
- `project_name/wtrx/models.py` -- BasePage, HeroMixin, core abstract models.
- `project_name/wtrx/images.py` -- CustomImage model.
- `project_name/home/`, `pages/`, `forms/` -- Page type apps (site-specific layer).
- `templates/` -- Global Django templates (NOT per-app).
- `static_src/` -- Frontend source (Tailwind, JS, Sass).
- `static_compiled/` -- Tailwind CLI output (committed to repo).

## Build Commands

### Python (via Make)

```bash
make venv                                # Create .venv and install all dependencies
make migrate                             # Run migrations
make createsuperuser                     # Create admin user
make dev                                 # Dev server at localhost:8000
make setup                               # Interactive initial setup
make test                                # Run all tests
```

For granular test runs, call manage.py directly:

```bash
python manage.py test project_name.wtrx               # Run tests for wtrx app only
python manage.py test project_name.wtrx.tests.test_blocks  # Run a single test module
python manage.py test project_name.wtrx.tests.test_blocks.TestImageBlock  # Single test class
python manage.py test project_name.wtrx.tests.test_blocks.TestImageBlock.test_required_fields  # Single test
```

### Frontend

```bash
npm install                              # Install Node dependencies (once only)
make build                               # Dev CSS build (Tailwind CLI)
make build-prod                          # Production CSS build (minified)
make watch                               # Watch mode (rebuilds CSS on change)
```

### Docker

```bash
docker build -t wagtail-wtr .            # Build image
make load-data                           # Load fixtures + migrate + collectstatic
```

### Template Testing

```bash
# Verify the template works with wagtail start
wagtail start --template=. testproject /tmp/testproject
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
  Use absolute imports with `{{ project_name }}` prefix for cross-app imports
  (e.g., `from {{ project_name }}.wtrx.blocks import BodyStreamBlock`).
- **Strings**: Use double quotes for human-readable strings (help_text, verbose_name).
  Use single quotes for identifiers and keys (dict keys, field names, choice values).
- **Models**: One model per logical concern. Use abstract models for shared behavior.
  Always set `related_name='+'` on ForeignKeys that don't need reverse relations.
  Use `on_delete=models.SET_NULL` for optional image/page ForeignKeys.
- **Blocks**: Each block class must have a docstring and a `class Meta` with `icon`
  and `template` pointing to `components/streamfield/blocks/<name>.html`
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

- **CRITICAL**: All `.html` template files MUST be wrapped in
  `{% verbatim %}{% endverbatim %}` as the first and last lines.
  This is required for `wagtail start --template` compatibility — the template
  engine processes ALL files in the repo (including `.html`) when generating a
  new project, and without `{% verbatim %}`, any `{% load %}` or `{{ variable }}`
  tag in an HTML file will cause a `TemplateSyntaxError` and abort the project
  creation. The `{% verbatim %}` wrapper prevents the engine from parsing those
  tags during project creation; at runtime the outer `{% verbatim %}` tags are
  not present (they were only in the template source).
  - HTML files NEVER contain `{{ project_name }}` substitution — that only
    happens in `.py` files (e.g., `manage.py`, `settings/base.py`, `urls.py`).
    The `{% verbatim %}` wrapper is purely to prevent Django's template parser
    from crashing on `{% load %}` calls during project creation.
  - Example `.py` usage (substituted at project creation):
    `os.environ.setdefault('DJANGO_SETTINGS_MODULE', '{{ project_name }}.settings.dev')`
  - Example `.html` file structure:
    ```
    {% verbatim %}
    {% load i18n wagtailcore_tags %}
    {% extends "base.html" %}
    {% block content %}...{% endblock %}
    {% endverbatim %}
    ```
- **Internationalization**: All user-facing UI strings in templates MUST use
  `{% trans "string" %}` (or `{% blocktrans %}...{% endblocktrans %}` for
  multi-word strings with variables). Add `{% load i18n %}` at the top of any
  template that contains translatable strings. This includes button defaults
  ("Donate", "Sign Up", "Read more"), pagination labels, error messages,
  copyright fallback text, and form feedback messages. Block content entered
  by editors is translated via wagtail-localize — only hardcoded UI strings
  need `{% trans %}`.
- **Tailwind**: Use semantic design tokens only. Never use raw color values.
  - Correct: `bg-primary-600`, `font-heading`, `text-neutral-800`
  - Wrong: `bg-blue-600`, `font-serif`, `text-gray-800`
- **Components**: Reusable UI lives in `templates/components/`. Block templates
  live in `templates/components/streamfield/blocks/`.
- **Indentation**: 4 spaces for HTML. Use Wagtail template tags
  (`wagtailcore_tags`, `wagtailimages_tags`, etc.) as needed.

### JavaScript

- Vanilla JS only (no frameworks). Class-based components with selector-based init.
- ES module syntax. 4-space indentation. Semicolons required.

### CSS

- Entry point: `static_src/css/main.css`.
- Use `@tailwind base; @tailwind components; @tailwind utilities;` directives.
- Built with Tailwind CLI (`make build` / `make build-prod` / `make watch`).
- Output goes to `static_compiled/css/main.css` (committed to repo).
- Minimize custom CSS. Prefer Tailwind utilities in templates.
- If component classes are needed, define in `@layer components {}`.

## Architecture Rules

1. **wtrx/ is self-contained**: It MUST NOT import from `home/`, `pages/`,
   `forms/`, or any other site-specific app. Those apps import FROM `wtrx/`.
2. **No circular imports**: Page-type apps depend on `wtrx/`, never the reverse.
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
- In the template repo, test paths are prefixed with `project_name.`
  (e.g., `project_name.wtrx.tests.test_blocks`). In a generated site they
  become `<projectname>.wtrx.tests.test_blocks`.
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

3. **TranslatableMixin on BasePage**: `BasePage` must include `TranslatableMixin`
   for wagtail-localize to work on all page types:
   `class BasePage(TranslatableMixin, Page)`.

   For `FormPage(BasePage, AbstractEmailForm)`, the full MRO resolves as:
   `FormPage → BasePage → TranslatableMixin → AbstractEmailForm → … → Page`.
    Django handles this correctly because `TranslatableMixin` does not itself
    inherit from `Page`. However, `TranslatableMixin` adds unique constraints
    that can produce unexpected migration conflicts if not handled carefully — run
    `make migrate` (or `python manage.py makemigrations --check`) after adding any new page model.

4. **`{% verbatim %}` in HTML files**: Every `.html` file must start with
   `{% verbatim %}` (first line) and end with `{% endverbatim %}` (last line).
   `wagtail start --template` runs the Django template engine over every file
   in the repo — including `.html` files — during project creation. Without
   `{% verbatim %}`, any `{% load wagtailcore_tags %}` or similar tag causes a
   `TemplateSyntaxError` and aborts project creation. The wrapper is only
   present in the template source; the generated project's files do not need it.
   Python files do NOT use verbatim — they contain `{{ project_name }}`
   which IS substituted at project-creation time.

5. **`hide_from_search` not `search_appearance`**: The field controlling search
   visibility on `BasePage` is named `hide_from_search` (boolean, default False).

6. **`static_compiled/` is committed**: The Tailwind CLI output directory
   `static_compiled/` is intentionally committed to the repo so that new
   projects generated from the template have working CSS/JS immediately without
   needing to run `npm install` and `npm run build` first.

7. **`SocialLinkBlock` must be a named class**: Do not use an anonymous
   StructBlock inline in `SocialSettings.social_links`. Define
   `class SocialLinkBlock(blocks.StructBlock)` explicitly so it serializes
   correctly in migrations and the Wagtail editor.

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
- **`AGENTS.md`** — update build commands, pitfalls, and architecture rules to match
  the current state of the repo. This file is the source of truth for agents.
- **`README.md`** — update commands, stack description, and project structure whenever
  anything user-facing changes.

These files should never fall out of sync with the actual repo. Update them in the
same commit as the code change they describe.

## Code Review Requirement

**Before creating any commit**, run the `code-reviewer` agent on all changed
files. Use the Task tool with `subagent_type: "code-reviewer"` and provide:
- A summary of what was built and why
- The full list of files changed
- Any specific areas of concern or uncertainty

Only proceed with the commit after the reviewer has responded and any issues
it raises have been addressed. This applies to all commits, including small
fixes.

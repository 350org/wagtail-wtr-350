# wagtail-wtr

> [!NOTE]
> **This project is in pre-alpha development.** We may introduce breaking changes without warning. Please review PR details regularly for summaries of changes when pulling new versions of this repo.

Wagtail build with common organizing features, web best practices, and modern dev tools out of the box.

Built by [With the Ranks](https://withtheranks.com), used as a starting point for campaign, nonprofit, and organizer websites, and updated with new features periodically.

Fork this repo and customize via Tailwind theme to build your own site, and merge upstream changes to get new features as they're released. See [#Customization](#customization) for more information.

Supports theming via semantic Tailwind design tokens, supports multiple languages,
contains a StreamField library with common organizing blocks like Signup and Donate, has integrations with common organizing platforms like Action Network and Actblue, features custom page types ready to extend and more.

The `wtrx/` app (repo root, sibling to `wagtail_wtr/`) contains core shared features and is designed for eventual extraction as a standalone pip package
(`wagtail-wtrx`), inspired by [CodeRed Extensions](https://github.com/coderedcorp/coderedcms), so that sites built on top of  `wagtail-wtr` can utilize future platform updates.

---

## Requirements

- Python 3.13+
- Node 20+ (see `.nvmrc`)
- PostgreSQL (production) or SQLite (dev)

---

## Quickstart

### 1. Fork or clone the repo

```bash
git clone https://github.com/withtheranks/wagtail-wtr.git mysite
cd mysite
```

### 2. Run the one-shot setup

```bash
make quickstart
```

This creates the virtual environment, installs Python and Node dependencies,
builds frontend assets, runs migrations, and optionally runs the interactive
site setup and superuser creation. When it finishes, start the dev server:

```bash
source .venv/bin/activate
make dev
```

**Or run each step manually:**

```bash
make venv
source .venv/bin/activate
npm install
make build
make migrate
make setup           # interactive: site name, donation platform, signup platform
make createsuperuser
make dev
```

Visit [http://localhost:8000/](http://localhost:8000/) for the site and
[http://localhost:8000/admin/](http://localhost:8000/admin/) for the Wagtail admin.

---

## Customization

### 1. Fork the repo on GitHub

Use the **Fork** button on GitHub, or with the GitHub CLI:

```bash
gh repo fork With-the-Ranks/wagtail-wtr --clone --remote
cd wagtail-wtr   # use your fork's name here if you renamed it on GitHub
```

If you fork manually, clone your fork and add the upstream remote:

```bash
git clone git@github.com:yourorg/your-site.git
cd your-site
git remote add upstream git@github.com:With-the-Ranks/wagtail-wtr.git
```

### 2. Complete initial setup

Follow the [Quickstart](#quickstart) steps above. The short version:

```bash
make quickstart
source .venv/bin/activate
make dev
```

### 3. Brand and configure your fork

- **Public site name**: set during `make setup` — stored in the Wagtail `Site` model
  (also editable later in Wagtail admin → Settings → Sites).
- **Admin interface label**: update `WAGTAIL_SITE_NAME` in `wagtail_wtr/settings/base.py`.
- **Brand colors and fonts**: edit `static_src/css/theme.css` (see [Customizing the theme](#customizing-the-theme)).

Everything else is covered in [What to customize](#what-to-customize) below.

### 4. Pulling upstream updates

When new blocks, bug fixes, or features land in this repo, pull them into your fork:

```bash
git fetch upstream
git merge upstream/main
```

Most upstream changes land in `wtrx/`, `templates/`, and
`static_src/css/main.css` — none of which you should be editing on your fork.
The only file likely to produce a conflict is `static_src/css/theme.css` if you
have customised your brand colors. Resolve by keeping your `@theme {}` block and
accepting upstream additions (e.g. new `[data-theme]` presets) from the merge.
After merging, run `make build` to regenerate `static_compiled/` from your local `theme.css`.

### 5. Contributing changes back upstream

If you build something reusable — a new block, a base model improvement, a
bug fix — you can contribute it back to `wagtail-wtr` via a pull request.

**Rule of thumb**: only code in `wagtail_wtr/wtrx/`, `templates/`, and shared
`static_src/` belongs upstream. Brand colors, site-specific page models, and
fork-specific configuration stay on your fork.

#### Step-by-step

1. **Identify the commit(s) to contribute.** Your fork's `main` may contain
   site-specific commits mixed in with reusable work. Use `git log --oneline`
   to find the relevant commit SHA(s).

2. **Create a feature branch off upstream `main`:**

   ```bash
   git fetch upstream
   git checkout -b feature/my-feature upstream/main
   ```

3. **Cherry-pick the reusable commit(s) onto the branch:**

   ```bash
   git cherry-pick <sha>
   ```

   If the commit bundles site-specific changes with reusable ones, split it
   using `git cherry-pick --no-commit <sha>` (applies the diff without
   committing), then `git reset HEAD` to unstage everything, then `git add -p`
   to selectively stage only the reusable hunks before committing.
   Alternatively, reconstruct the diff manually on the new branch.

4. **Push the branch to your fork (origin) and open a PR targeting upstream:**

   ```bash
   git push origin feature/my-feature
   ```

   Then open a PR on GitHub:
   - Base repository: `With-the-Ranks/wagtail-wtr`, base branch: `main`
   - Head repository: your fork, head branch: `feature/my-feature`

   GitHub shows a **"compare across forks"** link on the upstream repo's
   Pull Requests page. The direct URL pattern is:
   ```
   https://github.com/With-the-Ranks/wagtail-wtr/compare/main...<yourorg>:feature/my-feature
   ```

5. **After the PR is merged**, rebase your fork's `main` onto upstream so the
   duplicate commit is cleanly dropped:

   ```bash
   git fetch upstream
   git checkout main
   git rebase upstream/main
   git push origin main --force-with-lease
   ```

   If the upstream maintainer merged the PR without changes, Git detects the
   equivalent patch and skips it automatically. If the commit was amended or
   squash-merged upstream, you may see a small conflict — resolve it with
   `git rebase --skip` to drop the duplicate. After the rebase your fork's
   `main` should be ahead by only your site-specific commits and 0 commits
   behind upstream.

---

## What to customize

### Edit freely — this is your site

| File / directory | What to change |
|---|---|
| `static_src/css/theme.css` | Brand colors (`--color-primary-*`, etc.), fonts, theme presets |
| `wagtail_wtr/settings/base.py` | `WAGTAIL_SITE_NAME`, `WTRX_DONATION_PLATFORM`, `WTRX_SIGNUP_PLATFORM`, `LANGUAGES` |
| `templates/` | Override or extend any template (shadow `templates/wtrx/<path>`) |
| `static_src/javascript/` | Add site-specific JS components |
| Wagtail admin | Settings > Branding, Navigation, Footer, Social, Integrations |

### Don't edit — pull upstream cleanly

| File / directory | Why |
|---|---|
| `wtrx/` | Core reusable app — blocks, page models, settings models, views, hooks. Upstream changes land here. |
| `static_src/css/main.css` | Tailwind infrastructure — imports, plugins, base layer. Leaving it unedited ensures conflict-free upstream merges. |

### Extend, don't modify

- **Page models**: all built-in page types (`HomePage`, `ContentPage`, `IndexPage`, `FormPage`) live in `wtrx/` — use them as-is. To add site-specific page types, create a new app and subclass `BasePage` and `HeroMixin` from `wtrx/`.
- **StreamField blocks**: use `BodyStreamBlock` as-is, or subclass it to add site-specific blocks (see [Customizing blocks](#customizing-blocks))
- **Settings models**: create new `BaseSiteSetting` subclasses (from `wagtail.contrib.settings`) in your own app if you need additional settings panels beyond what `wtrx/` already provides.

### Customizing blocks

If your fork needs a modified version of an existing block (e.g. adding a field to
`CardBlock`), subclass it at the site level rather than editing `wtrx/` directly.
Wagtail's `DeclarativeSubBlocksMetaclass` merges parent and child block definitions
via the MRO, so a subclass only needs to redeclare the blocks it wants to change.

**Example: adding a subtitle to CardBlock**

Create a site-level blocks module (e.g. `wagtail_wtr/mysite/blocks.py`):

```python
from django.utils.translation import gettext_lazy as _
from wagtail.blocks import CharBlock, ListBlock

from wtrx.blocks import (
    BodyStreamBlock,
    CardBlock,
    CardGridBlock,
    SectionBlock,
    SectionContentBlock,
)


class SiteCardBlock(CardBlock):
    """CardBlock with an additional subtitle field."""
    subtitle = CharBlock(required=False, label=_("Subtitle"))


class SiteCardGridBlock(CardGridBlock):
    """CardGridBlock that uses SiteCardBlock."""
    cards = ListBlock(SiteCardBlock(), min_num=2, max_num=12, label=_("Cards"))


class SiteSectionContentBlock(SectionContentBlock):
    """Override card inside sections."""
    card = SiteCardBlock()
    card_grid = SiteCardGridBlock()


class SiteSectionBlock(SectionBlock):
    content = SiteSectionContentBlock()


class SiteBodyStreamBlock(BodyStreamBlock):
    """Site-level override that swaps in custom blocks."""
    card = SiteCardBlock()
    card_grid = SiteCardGridBlock()
    section = SiteSectionBlock()
```

Then update page models to use `SiteBodyStreamBlock` (in a new site-specific app):

```python
# mysite/models.py
from mysite.blocks import SiteBodyStreamBlock

class HomePage(BasePage, HeroMixin):
    body = StreamField(SiteBodyStreamBlock(), ...)
```

**Key points:**

- `wtrx/` stays untouched — upstream merges are clean.
- `SiteCardBlock` inherits all upstream fields, validation, and template from
  `CardBlock`. If upstream adds a field, your subclass gets it automatically.
- `SectionContentBlock` exists specifically to support this pattern — it's a named
  `StreamBlock` subclass so you can override individual child blocks without
  duplicating the full 17-entry block list.
- The only merge friction is the import-line changes in `mysite/models.py` — trivial one-line conflicts.
- **Template overrides**: block templates live in `templates/components/streamfield/blocks/`.
  You can modify them directly on your fork. When `wtrx` is extracted to a pip
  package, Django's template resolution will prefer your project-level templates
  over the package defaults.

---

## What's included

### Page types

| Page type | Description |
|---|---|
| `HomePage` | Site root with hero + StreamField body |
| `ContentPage` | General-purpose content page with hero + body |
| `IndexPage` | Auto-lists child pages in a card grid; optional intro + body |
| `FormPage` | Wagtail form builder with AJAX submission + email notification |

### StreamField blocks (15)

| Category | Blocks |
|---|---|
| Content | Text, Heading, Image, Video, Button, Quote, Custom embed, Table |
| Layout | Section (with background/padding), Card Grid, Accordion |
| Composite | Callout (image + text side-by-side), Hero (mid-page) |
| Cards | Card, Person Card |
| Actions | Donate, Signup (wagtail\_forms / Action Network / link variants) |

### Site settings (5 panels)

- **Branding & SEO** — logo, favicon, default meta image, site description
- **Navigation** — primary nav links, CTA button
- **Footer** — footer nav sections, copyright text
- **Social** — social platform links
- **Integrations** — donation platform (ActBlue), signup platform (wagtail_forms / Action Network)

### Core features

- Semantic Tailwind design tokens (`bg-primary-600`, `font-heading`, etc.) — customize
  by editing `static_src/css/theme.css`
- Multi-lingual from day one via [wagtail-localize](https://github.com/wagtail/wagtail-localize)
- AJAX form submission (FormPage + SignupBlock)
- Custom image model with focal point CSS
- Production-ready: WhiteNoise, gunicorn, django-storages (S3), dj-database-url

---

## Make commands

```
make quickstart       Full local dev setup: venv + npm install + build + migrate + optional setup/superuser
make venv             Create .venv and install all dependencies
make dev              Run development server + Tailwind CSS watcher (localhost:8000)
make dev-server       Run development server only (no CSS watcher)
make build            Build CSS + JS — development (Tailwind CLI + JS + fonts + images copy)
make build-prod       Build CSS + JS — production (minified CSS + JS + fonts + images copy)
make build-js         Copy JS source to static_compiled/js/
make build-fonts      Copy font files to static_compiled/fonts/
make build-images     Copy static images to static_compiled/images/
make watch            Watch and rebuild CSS on file changes (standalone)
make migrate          Run database migrations
make createsuperuser  Create admin user
make setup            Interactive initial site setup
make test             Run test suite
make load-data        Migrate + load demo fixtures + collectstatic
make provision        Provision AWS S3 bucket + IAM user (see make help)
```

---

## Project structure

```
wagtail-wtr/
├── wtrx/                   # Core reusable app (don't edit on client sites)
│   ├── blocks/             # StreamField blocks (content, layout, composite, cards, actions)
│   ├── models.py           # BasePage, HeroMixin, HomePage, ContentPage, IndexPage, FormField, FormPage
│   ├── views.py            # search() view
│   ├── site_settings.py
│   ├── images.py           # CustomImage
│   ├── templatetags/
│   └── wagtail_hooks.py
├── wagtail_wtr/            # Django project package (settings, urls, wsgi only)
│   └── settings/
│       ├── base.py
│       ├── dev.py
│       └── production.py
├── templates/
├── static_src/             # Tailwind CSS source + vanilla JS + font files
├── static_compiled/        # Tailwind CLI output (gitignored; run make build)
├── Makefile
├── pyproject.toml
└── package.json
```

`wtrx/` is the stable core. All page models and the search view live there. To add
site-specific page types, create a new app and subclass `BasePage`; don't edit `wtrx/` directly.

---

## Customizing the theme

Edit the `@theme {}` block in `static_src/css/theme.css` to change the semantic design tokens:

```css
@theme {
  /* Replace these color scales with your brand palette */
  --color-primary-50:  #f0f9ff;
  --color-primary-500: #0ea5e9;
  --color-primary-600: #0284c7;
  /* ... full scale 50–950 ... */

  /* Font stacks */
  --font-heading: 'Your Heading Font', system-ui, sans-serif;
  --font-body:    'Your Body Font', system-ui, sans-serif;
}
```

All templates use only semantic tokens (`bg-primary-600`, `font-heading`, etc.), so
changing the `@theme {}` values immediately re-themes the entire site. Rebuild after changes:

```bash
make build-prod
```

`theme.css` also ships named theme presets (`[data-theme="grassroots"]`, etc.) as
CSS overrides — no rebuild needed when switching between presets at runtime. Client
forks that don't use these can delete those blocks.

---

## Languages

Each language is its own page tree under Root. URLs are addressed by country
rather than by language code, which is what the sites already publish:

```
Root
├── Home (en)          ->  example.org/
├── Brasil (pt-br)     ->  example.org/brasil
│   └── English (en-br) -> example.org/brasil/en
├── France (fr-fr)     ->  example.org/france
├── Canada (en-ca)     ->  example.org/canada
│   └── Français (fr-ca) -> example.org/canada/fr
└── Español (es)       ->  example.org/es
```

One rule covers every tree:

| Kind | Prefix | Example |
|---|---|---|
| A country site | the country slug | `pt-br` -> `/brasil` |
| A translation of a country site | that slug, then the language | `en-br` -> `/brasil/en` |
| A global language (no country site) | its own code | `es` -> `/es` |
| English (the default) | none | `/` |

A country slug carries no language segment of its own: `/brasil` *is* the
Portuguese site, `/canada` *is* the English one. A second language on that same
country site is a translation of it and nests underneath, so each country keeps
one address and one tree per language.

**A country translation needs its own language code.** One locale maps to
exactly one URL prefix, so `/brasil/en` cannot be served by the global `en`
locale — that one already owns `/`. Brazilian English is `en-br`, a separate
code with its own tree. Codes read `language-country`, matching the order of
the URL segments (`es-fr` -> `/france/es`).

A language with a single home keeps its plain code whatever its URL: German is
`de` and serves at `/germany`, and would only need a `de-de` if Germany gained
a second language. Plain `fr` and `es` are the other shape — global languages
with no country site of their own.

In the settings list a `# Countries` comment separates the two groups, and
labels follow the same split: a bare language name above it, `Language -
Country` below (`Portuguese - Brazil`, `Spanish - France`).

A country code inherits its base language's catalogue (`pt-br` reads
`locale/pt/`), so a country site needs no extra UI translation work. A mapped
language serves *only* at its prefix — `/pt-br/` and `/en-br/` both 404 — so
there is one canonical URL per tree.

A translated page is a real, separately editable page linked to its source, so
it can have its own slug (`/about/` -> `/brasil/sobre-nos/`) and can hold pages
that exist in one language only. An English-language *region* (`/australia/`)
is not a language and stays an ordinary section under the English Home.

Configured in `wagtail_wtr/settings/base.py`:

```python
WAGTAIL_CONTENT_LANGUAGES = LANGUAGES = [
    ("en", _("English")),
    ("es", _("Spanish")),          # global: /es
    # Countries
    ("pt-br", _("Portuguese - Brazil")),
    ("en-br", _("English - Brazil")),
]

WTRX_LANGUAGE_URL_PREFIXES = {
    "pt-br": "brasil",      # the country site
    "en-br": "brasil/en",   # a translation of it, nested
    # `es` has no entry, so it serves under its own code.
}
```

To add a language to an existing country site, add the code and its nested
prefix here, then create the `Locale`. Until that row exists the prefix does
not resolve, so the entry is inert — nothing is exposed by adding it early.

`WAGTAIL_CONTENT_LANGUAGES` lists every language any 350 site might need, so
one can be chosen in the admin without a deploy. A language becomes real when it
gets a `Locale` row, which is a separate, deliberate step:

```bash
make locales                             # report: what exists, what's available
make locales LOCALES="pt-br fr-fr"       # create those two
```

Only create what you will use: a `Locale` appears in every "translate into" menu,
and `Locale` FKs are `on_delete=PROTECT`, so once a page uses one it cannot be
removed. Settings > Locales can only offer languages already in the settings
list, so once every configured language has a row its "Add" button opens a form
with an empty dropdown and appears to do nothing.

### Converting an existing section into a language site

A country site that already exists as an English subtree (`/brasil/` under
Home) becomes a real language tree with:

```bash
python manage.py convert_section_to_locale 59 pt-br --dry-run
python manage.py convert_section_to_locale 59 pt-br
```

It does three things, and the third is the one that is easy to miss: it moves
the section root to Root level, retags every page beneath it (and their stored
revisions) to the target locale, and makes that root the locale's counterpart
of the **site root** — without which the tree has no URL at all, because
`Site.get_site_root_paths()` walks `root_page.get_translations()`. None of this
is possible in the admin: `Page.locale` is `editable=False`, and a page cannot
be moved to a parent in another locale.

Whether any URL changes depends on `WTRX_LANGUAGE_URL_PREFIXES`. A section
whose slug already matches its language's prefix (`/brasil/` for `pt-br`) keeps
every URL it had, so the conversion is invisible from outside; where a URL does
move, a permanent redirect is created per page. The dry run says which case you
are in:

```
Serves as   : the pt-br counterpart of 'Home' -> /brasil/
URLs        : unchanged (/brasil/ is already the pt-br prefix)
```

This is not wagtail-localize's "Translate this page" — that copies a page into
another locale and leaves the original behind, which is right for translating
`/about/` into Spanish and wrong here. These pages *are* the Brazilian site,
not a translation of anything: nothing is duplicated.

Flags: `--dry-run`, `--no-redirects`, and `--standalone` (give the section root
a fresh `translation_key` instead of the site root's — for a section
deliberately not meant to be served).

### Migrating the country sites (production runbook)

The one-time migration that turns 350.org's five English country subtrees into
language trees. Rehearsed against a restored production database; the figures
below are what that rehearsal produced.

| Page | Section | Locale | Pages | URL after |
|---|---|---|---|---|
| 51 | `canada` | `en-ca` | 43 | `/canada/` (unchanged) |
| 59 | `brasil` | `pt-br` | 885 | `/brasil/` (unchanged) |
| 60 | `france` | `fr-fr` | 362 | `/france/` (unchanged) |
| 61 | `indonesia` | `id` | 1423 | `/indonesia/` (unchanged) |
| 62 | `germany` | `de` | 234 | `/germany/` (unchanged) |

Every one of those slugs already matches its language's mapped prefix, so
**no URL moves and no redirects are created** — 2,947 pages change locale
without changing address.

**Order matters.** Deploy the code *before* converting. The prefix map has to
be live first; convert against a deployment that lacks it and the trees land at
`/pt-br/`, `/de/` and so on, and fixing that afterwards means real redirects.

```bash
# 1. Deploy the branch (settings, wtrx/i18n.py, compiled catalogues).

# 2. Back up the database. The conversion has no reverse command --
#    restoring this backup is the rollback.
pg_dump -Fc -f pre-locale-migration.dump "$DB"

# 3. Create the Locale rows. Nothing resolves at a prefix until these exist.
python manage.py bootstrap_locales en-ca pt-br fr-fr id de

# 4. Dry-run each one. Re-confirm the page IDs against production first --
#    these are from the rehearsal, not from prod itself. Every run must
#    report "URLs: unchanged"; if one does not, stop and find out why.
python manage.py convert_section_to_locale 51 en-ca --dry-run
python manage.py convert_section_to_locale 59 pt-br --dry-run
python manage.py convert_section_to_locale 60 fr-fr --dry-run
python manage.py convert_section_to_locale 61 id    --dry-run
python manage.py convert_section_to_locale 62 de    --dry-run

# 5. Convert. Each runs in its own transaction.
python manage.py convert_section_to_locale 51 en-ca
python manage.py convert_section_to_locale 59 pt-br
python manage.py convert_section_to_locale 60 fr-fr
python manage.py convert_section_to_locale 61 id
python manage.py convert_section_to_locale 62 de

# 6. Restart the application workers. NOT optional -- see below.
```

**Step 6 is the one that will bite you.** Wagtail caches the site root paths —
the table that maps a page's `url_path` to a URL — for an hour, in Django's
cache. Nothing in this project configures a cache backend, so that is
`LocMemCache`, which is **per-process**. The conversion clears it in the
management command's own process and nowhere else.

A worker still holding the pre-conversion copy sees only `/home/` as a root
path, matches none of the moved pages' new `url_path`s against it, and returns
`url = None` for every page in the converted tree. Nothing raises: navigation
links render empty, sitemap entries and canonical/hreflang tags vanish, and the
admin shows *"There is no site set up for this location"* on the section. The
pages themselves keep serving perfectly the whole time, because routing goes
through `Site.find_for_request()` rather than these cached paths — which is
exactly what makes it easy to miss. It clears itself within the hour; restarting
the workers makes it immediate and deterministic. The command prints a reminder
after each run.

**Verify** — each tree serves at its country slug with the right `lang`, and no
tree answers at its bare code:

```bash
curl -sI https://350.org/brasil/ | head -1      # 200
curl -s  https://350.org/brasil/ | grep -o 'lang="[^"]*"' | head -1
curl -sI https://350.org/pt-br/  | head -1      # 404 — one canonical URL per tree

# The sitemap must list every tree, not just the English one.
curl -s https://350.org/sitemap.xml | grep -c '<loc>'
curl -s https://350.org/sitemap.xml | grep -c '<loc>[^<]*/brasil/'

# Search must not leak other languages into a country site.
curl -s 'https://350.org/brasil/search/?query=clima' | grep -c '/france/'   # 0
```

Things the rehearsal confirmed you do **not** need to do:

- **No search reindex.** The database search backend filters `locale_id`,
  `path` and `depth` on the live columns, and the conversion changes no indexed
  text. Locale-scoped search was verified working immediately after.
- **No navigation or footer rework.** The overrides key off a `root_page` page
  reference, not a path, so they follow the sections from depth 3 to depth 2
  untouched.
- **No internal link repair.** Page IDs are stable; the pages move, they are
  not recreated. Only `depth`, `locale` and `translation_key` change, so an
  editor sitting on `/admin/pages/59/edit/` when the migration runs stays on
  the same page through a refresh, keeps their revision history, and can save
  normally — `locale` is not a form field, so their POST cannot revert it. The
  one visible change is in the explorer: the five sections are no longer
  children of Home, so anyone browsing Home's children sees them disappear to
  Root level.

Three expected consequences worth knowing before you see them:

- The five country home pages become translations of the English Home, so each
  declares the others as `hreflang` alternates. That linkage *is* what gives
  each tree its URL — it is not optional, and it is correct for home pages.
- **"Translate this page" disappears from the six home pages.** wagtail-localize
  shows that action only when the page has no counterpart in at least one
  `Locale`, and after the migration Home has one in all six. It is still
  offered on every other page, and it comes back on the homes the moment a new
  locale is added. Not a regression, and not a side effect of running
  `wagtail.locales` instead of `wagtail_localize.locales`.
- Wagtail's Locales screen will show six locales, and every "translate into"
  menu will offer them. A `Locale` with pages cannot be deleted
  (`on_delete=PROTECT`).

### What gets translated

Two separate things get translated:

| What | How |
|---|---|
| Page content | Wagtail admin, via wagtail-localize ("Translate this page") |
| UI chrome (buttons, pagination, form errors) | gettext catalogues: `make messages`, then `make compile-messages` |

`.po` files are committed; `.mo` files are build output (gitignored, compiled in
the Dockerfile). Identifier fields — ActionKit form IDs, anchor slugs, Fundraise
Up element IDs — are deliberately excluded from translation; see `IdentifierBlock`
in `wtrx/blocks/__init__.py`.

---

## Platform integrations

Set defaults in `settings/base.py`:

```python
WTRX_DONATION_PLATFORM = "none"          # none | actblue
WTRX_SIGNUP_PLATFORM = "wagtail_forms"   # wagtail_forms | action_network | none
```

Override per-site in the Wagtail admin under **Settings > Integrations**.

---

## Development

```bash
# `make dev` already runs the Tailwind watcher alongside the dev server.
# Run the watcher on its own (e.g. alongside `make dev-server`):
make watch

# Run tests
python manage.py test wtrx wagtail_wtr

# Run a specific test module
python manage.py test wtrx.tests.test_images

# Generate migrations after model changes
python manage.py makemigrations
python manage.py migrate
```

Create `wagtail_wtr/settings/local.py` for personal overrides (gitignored):

```python
from .dev import *

DATABASES = { ... }   # override as needed
DEBUG = True
```

---

## Deployment

### Render (recommended)

A `render.yaml` Blueprint is included. To deploy:

1. Push your fork to GitHub.
2. In the Render dashboard, click **New → Blueprint** and connect your repo.
3. Render auto-provisions a PostgreSQL database and generates a `SECRET_KEY`.
4. Set the required env vars in the Render dashboard (or in `render.yaml` before importing):
   - `ALLOWED_HOSTS` — your Render hostname, e.g. `mysite.onrender.com`
   - `WAGTAILADMIN_BASE_URL` — full public URL, e.g. `https://mysite.onrender.com`
5. Deploy. The Docker build compiles CSS/JS and installs Python deps.
   Render's `preDeployCommand` runs `collectstatic` (with S3 credentials available).
   On startup, `bin/start.sh` runs `migrate` then starts gunicorn — the health
   check responds immediately because collectstatic has already completed.

Copy `.env.example` to `.env` (gitignored) for local production-settings overrides.

### How it works

Ships with:

- Two-stage `Dockerfile`: Node 20 (Tailwind CLI build) → Python 3.13-slim (app)
- `preDeployCommand` (render.yaml): intended to run `collectstatic --noinput` with S3 credentials before the container starts — **see note below**
- `bin/start.sh` entrypoint: runs `migrate --noinput` then starts gunicorn immediately
- `/_health/` endpoint for zero-downtime deploy health checks
- `render.yaml` `preDeployCommand` runs `collectstatic` before the container takes traffic
- `whitenoise` for static file serving when S3 is not configured
- `gunicorn` as WSGI server with `$PORT` binding for Render compatibility
- `dj-database-url` for `DATABASE_URL` env var
- `django-storages[s3]` + `wagtail-storages` for S3 media and static (optional — see below)

> **Known issue — manual collectstatic after CSS-changing deploys (S3 path)**
>
> When `AWS_STORAGE_BUCKET_NAME` is set, `bin/start.sh` skips `collectstatic`
> because `render.yaml`'s `preDeployCommand` is supposed to run it before the
> container starts. However, `preDeployCommand` has not been confirmed to run
> reliably — its output does not appear in Render's runtime deploy logs.
>
> Until this is investigated and fixed, after any deploy that changes CSS, JS,
> or other static assets you must manually run collectstatic via the Render
> dashboard:
>
> 1. In the Render dashboard, open your service.
> 2. Click the **Shell** tab.
> 3. Run: `python manage.py collectstatic --noinput`
>
> This is tracked in PLAN.md Phase 17.

### Required environment variables

```
SECRET_KEY=...                          # auto-generated on Render
DATABASE_URL=postgres://...             # auto-wired on Render
ALLOWED_HOSTS=mysite.com,www.mysite.com
WAGTAILADMIN_BASE_URL=https://mysite.com
DJANGO_SETTINGS_MODULE=wagtail_wtr.settings.production
```

### AWS S3 storage (optional)

When `AWS_STORAGE_BUCKET_NAME` is set, **both** user-uploaded media (images, documents)
**and** collected static files (CSS, JS, fonts) are stored in S3 under separate prefixes:

- `{bucket}/media/` — user uploads
- `{bucket}/static/` — compiled static assets

Omit the variable to use WhiteNoise for static files and local filesystem for media.

#### Automated provisioning

Run `make provision` to create the S3 bucket and a scoped IAM user in one step.
The script uses your local AWS CLI profile — no credentials are typed into the script.

**1. Configure an AWS CLI profile** (if you haven't already):

```bash
aws configure --profile wagtail-wtr-provisioner
# Prompts for: Access Key ID, Secret Access Key, region, output format
```

**2. Run the provisioning script:**

```bash
make provision SITE=mysite ENV=production PROFILE=wagtail-wtr-provisioner
make provision SITE=mysite ENV=staging PROFILE=wagtail-wtr-provisioner
```

Omit `PROFILE` to use the default AWS CLI profile. `ENV` defaults to `production`.

The script will display the AWS account ID and authenticated identity before
making any changes, so you can confirm you're targeting the right account.

This creates:
- S3 bucket: `mysite-wagtail-wtr-production` (or `-staging`)
- IAM user: `mysite-wagtail-wtr-production` with an inline policy scoped to that bucket only

It then prints the four env vars to paste into the Render dashboard.

**Required IAM permissions for the profile you use:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Provisioning",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:HeadBucket",
        "s3:PutBucketPolicy",
        "s3:PutBucketCORS",
        "s3:PutPublicAccessBlock"
      ],
      "Resource": "arn:aws:s3:::*"
    },
    {
      "Sid": "IAMProvisioning",
      "Effect": "Allow",
      "Action": [
        "iam:CreateUser",
        "iam:GetUser",
        "iam:PutUserPolicy",
        "iam:CreateAccessKey"
      ],
      "Resource": "arn:aws:iam::*:user/*"
    },
    {
      "Sid": "STSGetCallerIdentity",
      "Effect": "Allow",
      "Action": "sts:GetCallerIdentity",
      "Resource": "*"
    }
  ]
}
```

Create this as a policy named `wagtail-wtr-provisioner` in **IAM → Policies → Create policy**
and attach it to your admin user. If your admin user already has `AdministratorAccess`,
no extra policy is needed.

#### Manual setup

If you prefer to create resources manually, set these env vars in the Render dashboard:

```
AWS_STORAGE_BUCKET_NAME=mysite-wagtail-wtr-production
AWS_S3_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_CUSTOM_DOMAIN=assets.mysite.com   # optional: CloudFront or custom domain
```

To provision a new S3 bucket and scoped IAM user automatically:

```bash
make provision SITE=mysite ENV=production
# optional: make provision SITE=mysite ENV=staging PROFILE=my-aws-profile
```

This creates the bucket, sets the public-read policy, and outputs the `AWS_ACCESS_KEY_ID`
and `AWS_SECRET_ACCESS_KEY` for a dedicated IAM user scoped to that bucket.

### SMTP email (optional)

When `EMAIL_HOST` is set, Django sends mail via SMTP (compatible with Mailgun,
AWS SES, Postmark, or any standard SMTP provider). Without it, emails are printed
to container logs (console backend).

```
EMAIL_HOST=smtp.mailgun.org
EMAIL_PORT=587
EMAIL_HOST_USER=postmaster@mg.mysite.com
EMAIL_HOST_PASSWORD=...
DEFAULT_FROM_EMAIL=hello@mysite.com
```

### Cloudflare cache invalidation (optional)

When Cloudflare is in front of your site, set these two environment variables and
the platform will automatically purge cached pages on publish and flush the entire
cache whenever site settings (branding, navigation, footer, social, integrations)
are saved.

```
CLOUDFLARE_BEARER_TOKEN=your-api-token
CLOUDFLARE_ZONE_ID=your-zone-id
```

**To get these values:**

1. **Zone ID** — in the Cloudflare dashboard, select your domain. The Zone ID
   appears in the right-hand panel under *API* on the Overview page.

2. **Bearer token** — go to **My Profile → API Tokens → Create Token**. Use the
   **Edit zone resources** template (or create a custom token) with these
   permissions:
   - Zone → Cache Purge → Purge
   - Zone Resources → Include → your specific zone (or all zones)

---

## License

MIT. See `LICENSE`.

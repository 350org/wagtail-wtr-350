# wagtail-wtr

Wagtail build with common organizing features, web best practices, and modern dev tools out of the box.

Built by [With the Ranks](https://withtheranks.com), used as a starting point for campaign, nonprofit, and organizer websites, and updated with new features periodically.

Fork this repo and customize via Tailwind theme to build your own site, and merge upstream changes to get new features as they're released. See [#Customization](#customization) for more information.

Supports theming via semantic Tailwind design tokens, supports multiple languages,
contains a StreamField library with common organizing blocks like Signup and Donate, has integrations with common organizing platforms like Action Network and Actblue, features custom page types ready to extend and more.

The `wtrx/` sub-app contains core shared features and is designed for eventual extraction as a standalone pip package
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

### 2. Set up the virtual environment and install dependencies

```bash
make venv
source .venv/bin/activate
npm install
```

### 3. Build frontend assets

```bash
make build
```

### 4. Run migrations and set up the site

```bash
make migrate
make setup       # interactive: site name, donation platform, signup platform
```

### 5. Create an admin user and start the dev server

```bash
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
make venv
source .venv/bin/activate
npm install
make build
make migrate
make setup          # sets site name, donation platform, signup platform
make createsuperuser
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

Most upstream changes land in `wagtail_wtr/wtrx/`, `templates/`, and
`static_src/css/main.css` — none of which you should be editing on your fork.
The only file likely to produce a conflict is `static_src/css/theme.css` if you
have customised your brand colors. Resolve by keeping your `@theme {}` block and
accepting upstream additions (e.g. new `[data-theme]` presets) from the merge.
After merging, run `make build` to regenerate `static_compiled/` from your local `theme.css`.

---

## What to customize

### Edit freely — this is your site

| File / directory | What to change |
|---|---|
| `static_src/css/theme.css` | Brand colors (`--color-primary-*`, etc.), fonts, theme presets |
| `wagtail_wtr/settings/base.py` | `WAGTAIL_SITE_NAME`, `WTRX_DONATION_PLATFORM`, `WTRX_SIGNUP_PLATFORM`, `LANGUAGES` |
| `wagtail_wtr/home/` | `HomePage` model and template |
| `wagtail_wtr/pages/` | Add or modify page types (`ContentPage`, `IndexPage`, new types) |
| `wagtail_wtr/forms/` | Customise form page behavior |
| `templates/` | Override or extend any template |
| `static_src/javascript/` | Add site-specific JS components |
| Wagtail admin | Settings > Branding, Navigation, Footer, Social, Integrations |

### Don't edit — pull upstream cleanly

| File / directory | Why |
|---|---|
| `wagtail_wtr/wtrx/` | Core reusable app — blocks, base models, settings models, hooks. Upstream changes land here. |
| `static_src/css/main.css` | Tailwind infrastructure — imports, plugins, base layer. Leaving it unedited ensures conflict-free upstream merges. |

### Extend, don't modify

- **Page models**: subclass `BasePage` and `HeroMixin` from `wtrx/` in your own apps (`home/`, `pages/`, etc.)
- **StreamField blocks**: use `BodyStreamBlock` as-is, or subclass it to add site-specific blocks
- **Settings models**: create new `BaseSiteSetting` subclasses (from `wagtail.contrib.settings`) in your own apps if you need additional settings panels beyond what `wtrx/` already provides.

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
| Content | Text, Image, Video, Button, Quote, Raw HTML, Table |
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
- Custom user model
- Production-ready: WhiteNoise, gunicorn, django-storages (S3), dj-database-url

---

## Make commands

```
make venv             Create .venv and install all dependencies
make dev              Run development server (localhost:8000)
make build            Build CSS + JS — development (Tailwind CLI + JS copy)
make build-prod       Build CSS + JS — production (minified CSS + JS copy)
make build-js         Copy JS source to static_compiled/js/
make watch            Watch and rebuild CSS on file changes
make migrate          Run database migrations
make createsuperuser  Create admin user
make setup            Interactive initial site setup
make test             Run test suite
make load-data        Migrate + load demo fixtures + collectstatic
```

---

## Project structure

```
wagtail-wtr/
├── wagtail_wtr/
│   ├── wtrx/               # Core reusable app (don't edit on client sites)
│   │   ├── blocks/         # StreamField blocks (content, layout, composite, cards, actions)
│   │   ├── models.py       # BasePage, HeroMixin
│   │   ├── site_settings.py
│   │   ├── images.py       # CustomImage
│   │   ├── templatetags/
│   │   └── wagtail_hooks.py
│   ├── home/               # HomePage
│   ├── pages/              # ContentPage, IndexPage
│   ├── forms/              # FormPage
│   ├── users/              # Custom user model
│   ├── search/             # Search view
│   └── settings/
│       ├── base.py
│       ├── dev.py
│       └── production.py
├── templates/
├── static_src/             # Tailwind CSS source + vanilla JS
├── static_compiled/        # Tailwind CLI output (committed)
├── Makefile
├── pyproject.toml
└── package.json
```

`wtrx/` is the stable core. Site-specific code goes in `home/`, `pages/`, `forms/`,
or new apps. Extend or override `wtrx/` models and blocks; don't edit them directly.

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

## Adding languages

In `wagtail_wtr/settings/base.py`, uncomment or add languages:

```python
WAGTAIL_CONTENT_LANGUAGES = LANGUAGES = [
    ("en", "English"),
    ("es", "Spanish"),
]
```

Translations are managed via the Wagtail admin using wagtail-localize.

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
# Watch mode: rebuilds CSS on file changes
make watch

# Run tests
python manage.py test wagtail_wtr

# Run a specific test module
python manage.py test wagtail_wtr.wtrx.tests.test_images

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

Ships with:

- `Dockerfile` (Python 3.13-slim)
- `whitenoise` for static file serving
- `gunicorn` as WSGI server
- `dj-database-url` for `DATABASE_URL` env var
- `django-storages[s3]` + `wagtail-storages` for S3 media

Required environment variables in production:

```
SECRET_KEY=...
DATABASE_URL=postgres://...
ALLOWED_HOSTS=mysite.com,www.mysite.com
```

---

## License

MIT. See `LICENSE`.

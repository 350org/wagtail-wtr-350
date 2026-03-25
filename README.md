# wagtail-wtr

A Wagtail project template for campaign, nonprofit, and organizer websites.

Used via `wagtail start --template` to scaffold a new site with sensible defaults:
semantic Tailwind design tokens, multi-lingual support via wagtail-localize, AJAX
form submission, a 15-block StreamField library, and 4 page types ready to extend.

Contains a `wtrx/` sub-app designed for eventual extraction as a pip package
(`wagtail-wtrx`).

---

## Requirements

- Python 3.13+
- Node 20+ (see `.nvmrc`)
- PostgreSQL (production) or SQLite (dev)
- [Wagtail CLI](https://docs.wagtail.org/en/stable/reference/management_commands.html#start)

---

## Quickstart

### 1. Create a new project

```bash
pip install wagtail
wagtail start --template=https://github.com/withtheranks/wagtail-wtr/archive/main.zip mysite /path/to/mysite
cd /path/to/mysite
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
[http://localhost:8000/cms/](http://localhost:8000/cms/) for the Wagtail admin.

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
  by editing `tailwind.config.js`
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
make build            Build CSS — development (Tailwind CLI)
make build-prod       Build CSS — production (minified)
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
mysite/
├── mysite/
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

Edit `tailwind.config.js` to change the semantic design tokens:

```js
theme: {
  extend: {
    colors: {
      primary: { /* replace with your brand color scale */ },
      secondary: { /* ... */ },
      accent: { /* ... */ },
      neutral: { /* ... */ },
    },
    fontFamily: {
      heading: ['Your Heading Font', 'sans-serif'],
      body: ['Your Body Font', 'sans-serif'],
    },
  },
},
```

All templates use only semantic tokens (`bg-primary-600`, `font-heading`, etc.), so
changing the config immediately re-themes the entire site. Rebuild after changes:

```bash
make build-prod
```

---

## Adding languages

In `mysite/settings/base.py`, uncomment or add languages:

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

# Run a specific test
python manage.py test mysite.wtrx.tests.test_blocks
```

Create `mysite/settings/local.py` for personal overrides (gitignored):

```python
from .dev import *

DATABASES = { ... }   # override as needed
DEBUG = True
```

---

## Deployment

The template ships with:

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

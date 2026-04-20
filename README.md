# wagtail-wtr

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
- `whitenoise` for static file serving from the container
- `gunicorn` as WSGI server
- `dj-database-url` for `DATABASE_URL` env var
- `django-storages[s3]` + `wagtail-storages` for S3 media (optional — see below)

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

### AWS S3 media storage (optional)

When `AWS_STORAGE_BUCKET_NAME` is set, user-uploaded media (images, documents) is
stored in S3. Omit the variable to use local filesystem storage instead.

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
AWS_S3_CUSTOM_DOMAIN=media.mysite.com   # optional: CloudFront or custom domain
```

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

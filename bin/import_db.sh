#!/usr/bin/env bash
# bin/import_db.sh
#
# Restore a Postgres database backup (a pg_dump in custom/directory/tar
# format, or a plain-text .sql dump) into a local Postgres database for
# development, then point .env at it.
#
# Usage:
#   bash bin/import_db.sh <backup-file-or-dir> [db-name] [--force]
#
# Examples:
#   bash bin/import_db.sh ~/Downloads/prod.dump
#   bash bin/import_db.sh ~/Downloads/prod.dump wtr350
#   bash bin/import_db.sh ~/Downloads/prod.dump wtr350 --force
#
# Invoked via Makefile:
#   make import-db BACKUP=~/Downloads/prod.dump
#   make import-db BACKUP=~/Downloads/prod.dump DB=wtr350
#
# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------
#
# A local Postgres server reachable at localhost:5432, with a role matching
# your OS username that can create databases (on Fedora/most distros'
# `postgres` package, local TCP connections are trusted by default — no
# password needed. If `psql -h localhost -U postgres` prompts for a password
# or refuses the connection, your pg_hba.conf differs; grant your role
# CREATEDB, e.g.: `sudo -u postgres createuser --createdb --superuser $(whoami)`).
#
# pg_restore/psql/createdb/dropdb come from the postgresql-client package,
# already required to talk to production Postgres.
#
# ---------------------------------------------------------------------------
# What this does
# ---------------------------------------------------------------------------
#
# 1. Drops and recreates the target database (confirms first, unless --force).
# 2. Restores the backup — pg_restore for custom/directory/tar dumps (the
#    default from `pg_dump -Fc`), psql for plain-text .sql dumps.
# 3. Runs `manage.py migrate` so a backup taken before the current checkout's
#    migration state still ends up consistent.
# 4. Writes/updates DATABASE_URL in .env (created from .env.example first if
#    .env doesn't exist yet).
#
# Restores with --no-owner --no-privileges, since backups taken from Render/
# Divio are owned by a role that doesn't exist locally; the connecting role
# becomes the owner instead.
#
# Postgres-specific extensions in production dumps (hstore, pg_trgm,
# btree_gin, etc.) have no sqlite equivalent, so this script only targets
# Postgres — don't try to convert a backup like this into db.sqlite3.

set -euo pipefail

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

BACKUP=""
DB_NAME="wtr350"
FORCE=false
_POSITIONAL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)
            FORCE=true
            shift
            ;;
        -*)
            echo "Error: unknown option '$1'." >&2
            echo "Usage: bash bin/import_db.sh <backup-file-or-dir> [db-name] [--force]" >&2
            exit 1
            ;;
        *)
            case "$_POSITIONAL" in
                0) BACKUP="$1" ;;
                1) DB_NAME="$1" ;;
                *) echo "Error: unexpected positional argument '$1'." >&2
                   echo "Usage: bash bin/import_db.sh <backup-file-or-dir> [db-name] [--force]" >&2
                   exit 1 ;;
            esac
            (( _POSITIONAL++ )) || true
            shift
            ;;
    esac
done

if [[ -z "$BACKUP" ]]; then
    echo "Error: <backup-file-or-dir> argument is required." >&2
    echo "Usage: bash bin/import_db.sh <backup-file-or-dir> [db-name] [--force]" >&2
    echo "       make import-db BACKUP=~/Downloads/prod.dump" >&2
    exit 1
fi

if [[ ! -e "$BACKUP" ]]; then
    echo "Error: backup path '$BACKUP' does not exist." >&2
    exit 1
fi

DB_USER="$(whoami)"
DB_HOST="localhost"

step() {
    echo "→ $*"
}

psql_admin() {
    psql -h "$DB_HOST" -U postgres -v ON_ERROR_STOP=1 "$@"
}

# ---------------------------------------------------------------------------
# Check dependencies
# ---------------------------------------------------------------------------

for cmd in psql pg_restore createdb dropdb; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "Error: '$cmd' is not installed (postgresql-client package)." >&2
        exit 1
    fi
done

if ! psql_admin -tAc "SELECT 1" &>/dev/null; then
    echo "Error: can't connect to Postgres at $DB_HOST:5432 as role 'postgres'." >&2
    echo "  Is a local Postgres server running? See the Requirements section" >&2
    echo "  at the top of this script for setup." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Detect backup format
# ---------------------------------------------------------------------------

FORMAT="plain"
if [[ -d "$BACKUP" ]]; then
    FORMAT="directory"
elif pg_restore --list "$BACKUP" &>/dev/null; then
    FORMAT="custom"
fi

step "Backup: $BACKUP (format: $FORMAT)"

# ---------------------------------------------------------------------------
# Drop and recreate the target database
# ---------------------------------------------------------------------------

DB_EXISTS=false
if [[ "$(psql_admin -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" == "1" ]]; then
    DB_EXISTS=true
fi

if [[ "$DB_EXISTS" == "true" && "$FORCE" != "true" ]]; then
    echo ""
    echo "Database '$DB_NAME' already exists and will be dropped and recreated."
    echo "Any local data in it will be lost."
    echo ""
    read -r -p "Proceed? [y/N] " CONFIRM
    if [[ "${CONFIRM,,}" != "y" ]]; then
        echo "Aborted."
        exit 0
    fi
    echo ""
fi

if [[ "$DB_EXISTS" == "true" ]]; then
    step "Dropping existing database '$DB_NAME'"
    # Terminate other connections first — DROP DATABASE fails while any
    # session (e.g. a running `manage.py runserver`) still holds it open.
    psql_admin -tAc "
        SELECT pg_terminate_backend(pid) FROM pg_stat_activity
        WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid()
    " >/dev/null
    dropdb -h "$DB_HOST" -U postgres "$DB_NAME"
fi

step "Creating database '$DB_NAME' (owner: $DB_USER)"
createdb -h "$DB_HOST" -U postgres -O "$DB_USER" "$DB_NAME"

# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

step "Restoring into '$DB_NAME'"

if [[ "$FORMAT" == "plain" ]]; then
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 -f "$BACKUP"
else
    # pg_restore's own exit code is unreliable here — it returns non-zero for
    # any warning (e.g. a role from the source server that doesn't exist
    # locally), even when every table and row restored fine. Check the
    # actual data afterwards instead of trusting $?.
    set +e
    pg_restore -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
        --no-owner --no-privileges -j4 "$BACKUP"
    set -e
fi

TABLE_COUNT="$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
if [[ "$TABLE_COUNT" -eq 0 ]]; then
    echo "Error: restore produced no tables in '$DB_NAME' — check the output above." >&2
    exit 1
fi
step "Restored $TABLE_COUNT tables"

# ---------------------------------------------------------------------------
# Wire up .env
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"
DATABASE_URL="postgres://${DB_USER}@${DB_HOST}:5432/${DB_NAME}"

if [[ ! -f "$ENV_FILE" ]]; then
    step "Creating .env from .env.example"
    cp "$REPO_ROOT/.env.example" "$ENV_FILE"
fi

if grep -q "^DATABASE_URL=" "$ENV_FILE"; then
    sed -i "s|^DATABASE_URL=.*|DATABASE_URL=$DATABASE_URL|" "$ENV_FILE"
else
    echo "DATABASE_URL=$DATABASE_URL" >> "$ENV_FILE"
fi
step "Set DATABASE_URL in .env"

if ! grep -q "^SECRET_KEY=.\+" "$ENV_FILE"; then
    GENERATED_KEY="$("$REPO_ROOT/.venv/bin/python" -c "import secrets; print(secrets.token_hex(50))" 2>/dev/null || python3 -c "import secrets; print(secrets.token_hex(50))")"
    sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$GENERATED_KEY|" "$ENV_FILE"
    step "Generated SECRET_KEY in .env"
fi

# ---------------------------------------------------------------------------
# Migrate
# ---------------------------------------------------------------------------

PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ -x "$PYTHON" ]]; then
    step "Running migrate to reconcile with this checkout"
    (cd "$REPO_ROOT" && "$PYTHON" manage.py migrate --noinput)
else
    echo "Note: .venv not found — skipping migrate. Run 'make migrate' once it's set up." >&2
fi

echo ""
echo "Done. $DB_NAME is ready at:"
echo "  $DATABASE_URL"
echo ""
echo "make dev will now use it automatically."

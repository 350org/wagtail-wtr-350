"""
Seed a "Usercentrics" entry in Settings > Integrations for every existing
IntegrationSettings row, matching the values that were previously hardcoded
in usercentrics_head.html / WTRX_USERCENTRICS_* env vars (see
0070_alter_integrationsettings_integrations.py and
wtrx.integrations.usercentrics).

Without this, deploying the move from env-var/template-hardcoded config to
Settings > Integrations would silently turn off the consent banner in
production the moment this migration runs, since
IntegrationSettings.get_usercentrics_config() would find no entry until an
editor adds one by hand -- a compliance regression, not just a cosmetic one.

Idempotent: a site whose `integrations` StreamField already has a
"usercentrics" entry (e.g. re-running this after an editor already added one)
is left untouched.
"""

import json
import uuid

from django.db import migrations

DEFAULT_VALUE = {
    "enabled": True,
    "settings_id": "AelB3mtRNvAY5D",
    "script_version": "1.1.4",
    "reload_on_opt_in_service_ids": "BJz7qNsdj-7",
    "deactivate_blocking_service_ids": "BJ59EidsWQ,gIwEsybsHImyP9",
    "fallback_country": "DE",
    "manual_country_override": "",
}


def seed_usercentrics(apps, schema_editor):
    IntegrationSettings = apps.get_model("wtrx", "IntegrationSettings")
    for row in IntegrationSettings.objects.all():
        raw = list(row.integrations.raw_data)
        if any(entry.get("type") == "usercentrics" for entry in raw):
            continue
        raw.append(
            {
                "type": "usercentrics",
                "value": DEFAULT_VALUE,
                "id": str(uuid.uuid4()),
            }
        )
        row.integrations = json.dumps(raw)
        row.save(update_fields=["integrations"])


def noop_reverse(apps, schema_editor):
    """
    Not reversible: we can't tell a seeded entry from one an editor has since
    edited by hand, so reversing would risk discarding real configuration.
    """


class Migration(migrations.Migration):

    dependencies = [
        ("wtrx", "0070_alter_integrationsettings_integrations"),
    ]

    operations = [
        migrations.RunPython(seed_usercentrics, noop_reverse),
    ]

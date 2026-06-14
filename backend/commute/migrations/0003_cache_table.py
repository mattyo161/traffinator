from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # Creates the DatabaseCache table named in settings.CACHES (commute_cache).
    # Idempotent — skips if it already exists.
    call_command("createcachetable")


class Migration(migrations.Migration):

    dependencies = [
        ("commute", "0002_routegeometry_savedaddress_savedroute_and_more"),
    ]

    operations = [
        migrations.RunPython(create_cache_table, migrations.RunPython.noop),
    ]

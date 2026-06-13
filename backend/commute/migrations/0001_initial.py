from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Setting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=64, unique=True)),
                ("value", models.TextField()),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="TrafficSample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("origin_lat", models.FloatField()),
                ("origin_lng", models.FloatField()),
                ("dest_lat", models.FloatField()),
                ("dest_lng", models.FloatField()),
                ("vector", models.CharField(choices=[("departure", "departure"), ("arrival", "arrival")], max_length=10)),
                ("day_of_week", models.PositiveSmallIntegerField()),
                ("time_of_day", models.TimeField()),
                ("duration_min_s", models.PositiveIntegerField()),
                ("duration_typical_s", models.PositiveIntegerField()),
                ("duration_max_s", models.PositiveIntegerField()),
                ("distance_m", models.PositiveIntegerField(blank=True, null=True)),
                ("raw_response", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
        ),
        migrations.AddIndex(
            model_name="trafficsample",
            index=models.Index(fields=["vector", "day_of_week"], name="commute_tra_vector_2a1f7c_idx"),
        ),
        # Geometric modules for the 1-mile spatial cache radius. On Supabase,
        # enable `cube` and `earthdistance` from the dashboard if this fails.
        migrations.RunSQL(
            sql=[
                "CREATE EXTENSION IF NOT EXISTS cube;",
                "CREATE EXTENSION IF NOT EXISTS earthdistance;",
                "CREATE INDEX IF NOT EXISTS idx_sample_origin_earth ON commute_trafficsample USING gist (ll_to_earth(origin_lat, origin_lng));",
                "CREATE INDEX IF NOT EXISTS idx_sample_dest_earth ON commute_trafficsample USING gist (ll_to_earth(dest_lat, dest_lng));",
            ],
            reverse_sql=[
                "DROP INDEX IF EXISTS idx_sample_origin_earth;",
                "DROP INDEX IF EXISTS idx_sample_dest_earth;",
            ],
        ),
    ]

# Generated manually for recent plan context handoff.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tour_api", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TravelPlanSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(blank=True, db_index=True, max_length=64)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("profile", models.JSONField(blank=True, default=dict)),
                ("plan_text", models.TextField(blank=True)),
                ("places", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="travel_plan_snapshots",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="travelplansnapshot",
            index=models.Index(fields=["user", "updated_at"], name="tour_api_tr_user_id_2a6e67_idx"),
        ),
        migrations.AddIndex(
            model_name="travelplansnapshot",
            index=models.Index(fields=["session_key", "updated_at"], name="tour_api_tr_session_e4a807_idx"),
        ),
    ]

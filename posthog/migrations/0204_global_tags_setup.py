# Generated by Django 3.2.5 on 2022-02-01 22:51

import django.contrib.postgres.fields
import django.db.models.deletion
from django.db import migrations, models

import posthog.models.utils


class Migration(migrations.Migration):

    dependencies = [
        ("posthog", "0203_dashboard_permissions"),
    ]

    operations = [
        migrations.RemoveField(model_name="dashboard", name="tags",),
        migrations.RemoveField(model_name="insight", name="tags",),
        migrations.AddField(
            model_name="dashboard",
            name="deprecated_tags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=32),
                blank=True,
                db_column="tags",
                default=list,
                null=True,
                size=None,
            ),
        ),
        migrations.AddField(
            model_name="insight",
            name="deprecated_tags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=32),
                blank=True,
                db_column="tags",
                default=list,
                null=True,
                size=None,
            ),
        ),
        migrations.CreateModel(
            name="EnterpriseTaggedItem",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=posthog.models.utils.UUIDT, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tag", models.SlugField()),
                ("color", models.CharField(blank=True, max_length=400, null=True)),
                (
                    "action",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="posthog.action",
                    ),
                ),
                (
                    "dashboard",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="posthog.dashboard",
                    ),
                ),
                (
                    "event_definition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="posthog.eventdefinition",
                    ),
                ),
                (
                    "feature_flag",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="posthog.featureflag",
                    ),
                ),
                (
                    "insight",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="posthog.insight",
                    ),
                ),
                (
                    "property_definition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tags",
                        to="posthog.propertydefinition",
                    ),
                ),
                ("team", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="posthog.team")),
            ],
        ),
        migrations.AddConstraint(
            model_name="enterprisetaggeditem",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("dashboard__isnull", True),
                        ("insight__isnull", True),
                        ("event_definition__isnull", True),
                        ("property_definition__isnull", True),
                        ("action__isnull", True),
                        ("feature_flag__isnull", True),
                    ),
                    models.Q(
                        ("dashboard__isnull", False),
                        ("insight__isnull", True),
                        ("event_definition__isnull", True),
                        ("property_definition__isnull", True),
                        ("action__isnull", True),
                        ("feature_flag__isnull", True),
                    ),
                    models.Q(
                        ("dashboard__isnull", True),
                        ("insight__isnull", False),
                        ("event_definition__isnull", True),
                        ("property_definition__isnull", True),
                        ("action__isnull", True),
                        ("feature_flag__isnull", True),
                    ),
                    models.Q(
                        ("dashboard__isnull", True),
                        ("insight__isnull", True),
                        ("event_definition__isnull", False),
                        ("property_definition__isnull", True),
                        ("action__isnull", True),
                        ("feature_flag__isnull", True),
                    ),
                    models.Q(
                        ("dashboard__isnull", True),
                        ("insight__isnull", True),
                        ("event_definition__isnull", True),
                        ("property_definition__isnull", False),
                        ("action__isnull", True),
                        ("feature_flag__isnull", True),
                    ),
                    models.Q(
                        ("dashboard__isnull", True),
                        ("insight__isnull", True),
                        ("event_definition__isnull", True),
                        ("property_definition__isnull", True),
                        ("action__isnull", False),
                        ("feature_flag__isnull", True),
                    ),
                    models.Q(
                        ("dashboard__isnull", True),
                        ("insight__isnull", True),
                        ("event_definition__isnull", True),
                        ("property_definition__isnull", True),
                        ("action__isnull", True),
                        ("feature_flag__isnull", False),
                    ),
                    _connector="OR",
                ),
                name="at_most_one_related_object",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="enterprisetaggeditem",
            unique_together={
                ("tag", "dashboard", "insight", "event_definition", "property_definition", "action", "feature_flag")
            },
        ),
    ]
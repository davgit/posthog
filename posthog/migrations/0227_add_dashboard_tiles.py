# Generated by Django 3.2.12 on 2022-04-08 11:13

import structlog
from django.db import connection, migrations, models


def migrate_dashboard_insight_relations(apps, _) -> None:
    logger = structlog.get_logger(__name__)
    logger.info("starting_0227_add_dashboard_tiles")

    DashboardTile = apps.get_model("posthog", "DashboardTile")

    with connection.cursor() as cursor:
        """
        Fetch all of the insights that have a dashboard ID
        and don't already have a posthog_dashboardtile relation
        """
        cursor.execute(
            """
            SELECT old_relation.id, old_relation.dashboard_id, old_relation.layouts, old_relation.color
            FROM posthog_dashboarditem as old_relation
            LEFT JOIN posthog_dashboardtile new_relation
                ON new_relation.insight_id = old_relation.id AND new_relation.dashboard_id = old_relation.dashboard_id
            WHERE old_relation.dashboard_id IS NOT NULL -- has a dashboard id on the old relation
            AND old_relation.deleted = FALSE -- no point linking deleted insights
            AND new_relation.insight_id IS NULL -- no new relation yet
            ORDER BY old_relation.last_modified_at ASC;
        """
        )

        count = 0
        while True:
            page = cursor.fetchmany(1000)
            if not page:
                break
            DashboardTile.objects.bulk_create(
                [DashboardTile(insight_id=row[0], dashboard_id=row[1], layouts=row[2], color=row[3]) for row in page],
                ignore_conflicts=True,
            )
            count += len(page)

        logger.info("finished_0227_add_dashboard_tiles", migration_count=count)


def reverse(apps, _) -> None:
    DashboardTile = apps.get_model("posthog", "DashboardTile")
    # issues a single delete
    DashboardTile.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("posthog", "0226_longer_action_slack_message_format"),
    ]

    operations = [
        migrations.CreateModel(
            name="DashboardTile",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dashboard", models.ForeignKey(on_delete=models.deletion.CASCADE, to="posthog.dashboard")),
                ("insight", models.ForeignKey(on_delete=models.deletion.CASCADE, to="posthog.insight")),
                ("layouts", models.JSONField(default=dict)),
                ("color", models.CharField(blank=True, max_length=400, null=True)),
            ],
        ),
        migrations.AddField(
            model_name="dashboard",
            name="insights",
            field=models.ManyToManyField(
                blank=True, related_name="dashboards", through="posthog.DashboardTile", to="posthog.Insight"
            ),
        ),
        migrations.RunPython(migrate_dashboard_insight_relations, reverse),
    ]

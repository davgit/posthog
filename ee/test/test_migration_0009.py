import pytest
from django.contrib.contenttypes.models import ContentType

from posthog.test.base import TestMigrations


@pytest.mark.ee
class TagsTestCase(TestMigrations):

    migrate_from = "0008_global_tags_setup"  # type: ignore
    migrate_to = "0009_migrate_definitions_tags"  # type: ignore

    @property
    def app(self):
        return "ee"

    def setUpBeforeMigration(self, apps):
        EnterpriseEventDefinition = apps.get_model("ee", "EnterpriseEventDefinition")
        EnterprisePropertyDefinition = apps.get_model("ee", "EnterprisePropertyDefinition")

        self.event_definition = EnterpriseEventDefinition.objects.create(
            team_id=self.team.id, name="enterprise event", deprecated_tags=["a", "b", "c"]
        )
        self.property_definition_with_tags = EnterprisePropertyDefinition.objects.create(
            team_id=self.team.id, name="property def with tags", deprecated_tags=["b", "c", "d", "e"]
        )
        self.property_definition_without_tags = EnterprisePropertyDefinition.objects.create(
            team_id=self.team.id, name="property def without tags",
        )

    def test_tags_migrated(self):
        EnterpriseTaggedItem = self.apps.get_model("posthog", "EnterpriseTaggedItem")  # type: ignore
        EnterpriseEventDefinition = self.apps.get_model("ee", "EnterpriseEventDefinition")  # type: ignore
        EnterprisePropertyDefinition = self.apps.get_model("ee", "EnterprisePropertyDefinition")  # type: ignore

        event_definition = EnterpriseEventDefinition.objects.get(id=self.event_definition.id)
        self.assertEqual(event_definition.tags.count(), 3)
        self.assertEqual(list(event_definition.tags.values_list("tag", flat=True)), ["a", "b", "c"])

        property_definition_with_tags = EnterprisePropertyDefinition.objects.get(
            id=self.property_definition_with_tags.id
        )
        self.assertEqual(property_definition_with_tags.tags.count(), 4)
        self.assertEqual(list(property_definition_with_tags.tags.values_list("tag", flat=True)), ["b", "c", "d", "e"])

        property_definition_without_tags = EnterprisePropertyDefinition.objects.get(
            id=self.property_definition_without_tags.id
        )
        self.assertEqual(property_definition_without_tags.tags.count(), 0)

        self.assertEqual(EnterpriseTaggedItem.objects.all().count(), 7)
        self.assertEqual(EnterpriseTaggedItem.objects.order_by("tag").values("tag").distinct().count(), 5)

    def tearDown(self):
        EnterpriseEventDefinition = self.apps.get_model("ee", "EnterpriseEventDefinition")  # type: ignore
        EnterpriseEventDefinition.objects.filter(id=self.event_definition.id).delete()
        EnterprisePropertyDefinition = self.apps.get_model("ee", "EnterprisePropertyDefinition")  # type: ignore
        EnterprisePropertyDefinition.objects.filter(
            id__in=[self.property_definition_with_tags.id, self.property_definition_without_tags.id]
        ).delete()
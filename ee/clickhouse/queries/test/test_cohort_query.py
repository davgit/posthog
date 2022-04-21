from datetime import datetime, timedelta
from uuid import uuid4

from ee.clickhouse.materialized_columns.columns import materialize
from ee.clickhouse.models.event import create_event
from ee.clickhouse.queries.cohort_query import CohortQuery
from ee.clickhouse.util import ClickhouseTestMixin, snapshot_clickhouse_queries
from posthog.client import sync_execute
from posthog.models.action import Action
from posthog.models.action_step import ActionStep
from posthog.models.filters.filter import Filter
from posthog.models.person import Person
from posthog.test.base import BaseTest


def _create_event(**kwargs) -> None:
    pk = uuid4()
    kwargs.update({"event_uuid": pk})
    create_event(**kwargs)


def _make_event_sequence(team, distinct_id, interval_days, period_event_counts):
    for period_index, event_count in enumerate(period_event_counts):
        for _ in range(event_count):
            _create_event(
                team=team,
                event="$pageview",
                properties={},
                distinct_id=distinct_id,
                timestamp=datetime.now() - timedelta(days=interval_days * period_index, hours=1),
            )


class TestCohortQuery(ClickhouseTestMixin, BaseTest):
    @snapshot_clickhouse_queries
    def test_basic_query(self):

        action1 = Action.objects.create(team=self.team, name="action1")
        step1 = ActionStep.objects.create(
            event="$autocapture", action=action1, url="https://posthog.com/feedback/123", url_matching=ActionStep.EXACT,
        )

        # satiesfies all conditions
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$autocapture",
            properties={"$current_url": "https://posthog.com/feedback/123"},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=2),
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=1),
        )

        # doesn't satisfy action
        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$autocapture",
            properties={"$current_url": "https://posthog.com/feedback/123"},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(weeks=3),
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(days=1),
        )

        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "type": "OR",
                            "values": [
                                {
                                    "key": "$pageview",
                                    "event_type": "events",
                                    "time_value": 1,
                                    "time_interval": "day",
                                    "value": "performed_event",
                                    "type": "behavioural",
                                },
                                {
                                    "key": "$pageview",
                                    "event_type": "events",
                                    "time_value": 2,
                                    "time_interval": "week",
                                    "value": "performed_event",
                                    "type": "behavioural",
                                },
                            ],
                        },
                        {
                            "type": "AND",
                            "values": [
                                {
                                    "key": action1.pk,
                                    "event_type": "actions",
                                    "time_value": 2,
                                    "time_interval": "week",
                                    "value": "performed_event_first_time",
                                    "type": "behavioural",
                                },
                                {"key": "email", "value": "test@posthog.com", "type": "person"},
                            ],
                        },
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        # Since all props should be pushed down here, there should be no full outer join!
        self.assertTrue("FULL OUTER JOIN" not in q)

        self.assertEqual([p1.uuid], [r[0] for r in res])

    def test_performed_event(self):
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=2),
        )

        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(days=9),
        )

        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "time_value": 1,
                            "time_interval": "week",
                            "value": "performed_event",
                            "type": "behavioural",
                        }
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        self.assertEqual([p1.uuid], [r[0] for r in res])

    def test_performed_event_multiple(self):
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=2),
        )

        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=4),
        )

        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(days=9),
        )

        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "operator": "gte",
                            "operator_value": 1,
                            "time_value": 1,
                            "time_interval": "week",
                            "value": "performed_event_multiple",
                            "type": "behavioural",
                        }
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        self.assertEqual([p1.uuid], [r[0] for r in res])

    def test_stopped_performing_event(self):
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=10),
        )

        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(days=3),
        )

        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "time_value": 1,
                            "time_interval": "week",
                            "seq_time_value": 1,
                            "seq_time_interval": "week",
                            "value": "stopped_performing_event",
                            "type": "behavioural",
                        }
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        self.assertEqual([p1.uuid], [r[0] for r in res])

    def test_restarted_performing_event(self):
        pass

    def test_performed_event_first_time(self):
        pass

    def test_performed_event_sequence(self):
        pass

    def test_performed_event_regularly(self):
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )

        _make_event_sequence(self.team, "p1", 3, [1, 1, 1])
        # Filter for:
        # Regularly completed [$pageview] [at least] [1] times per
        # [3][day] period for at least [3] of the last [3] periods
        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "operator": "gte",
                            "operator_value": 1,
                            "time_interval": "day",
                            "time_value": 3,
                            "total_periods": 3,
                            "min_periods": 3,
                            "value": "performed_event_regularly",
                            "type": "behavioural",
                        }
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        self.assertEqual([p1.uuid], [r[0] for r in res])

    def test_performed_event_regularly_with_variable_event_counts_in_each_period(self):
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )
        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test2", "email": "test2@posthog.com"}
        )
        # p1 gets variable number of events in each period
        _make_event_sequence(self.team, "p1", 3, [0, 1, 2])
        # p2 gets 10 events in each period
        _make_event_sequence(self.team, "p2", 3, [2, 2, 2])

        # Filter for:
        # Regularly completed [$pageview] [at least] [2] times per
        # [3][day] period for at least [2] of the last [3] periods
        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "operator": "gte",
                            "operator_value": 2,
                            "time_interval": "day",
                            "time_value": 3,
                            "total_periods": 3,
                            "min_periods": 2,
                            "value": "performed_event_regularly",
                            "type": "behavioural",
                        }
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)
        self.assertEqual([p2.uuid], [r[0] for r in res])

        # Filter for:
        # Regularly completed [$pageview] [at least] [1] times per
        # [3][day] period for at least [2] of the last [3] periods
        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "operator": "gte",
                            "operator_value": 1,
                            "time_interval": "day",
                            "time_value": 3,
                            "total_periods": 3,
                            "min_periods": 2,
                            "value": "performed_event_regularly",
                            "type": "behavioural",
                        }
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)
        self.assertEqual(set([p1.uuid, p2.uuid]), set([r[0] for r in res]))

    @snapshot_clickhouse_queries
    def test_person_props_only(self):
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test1@posthog.com"}
        )
        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test", "email": "test2@posthog.com"}
        )
        p3 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p3"], properties={"name": "test3", "email": "test3@posthog.com"}
        )
        # doesn't match
        p4 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p4"], properties={"name": "test3", "email": "test4@posthog.com"}
        )

        filter = Filter(
            data={
                "properties": {
                    "type": "OR",
                    "values": [
                        {
                            "type": "OR",
                            "values": [
                                {"key": "email", "value": "test1@posthog.com", "type": "person"},
                                {"key": "email", "value": "test2@posthog.com", "type": "person"},
                            ],
                        },
                        {
                            "type": "AND",
                            "values": [
                                {"key": "name", "value": "test3", "type": "person"},
                                {"key": "email", "value": "test3@posthog.com", "type": "person"},
                            ],
                        },
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        # Since all props should be pushed down here, there should be no full outer join!
        self.assertTrue("FULL OUTER JOIN" not in q)

        self.assertCountEqual([p1.uuid, p2.uuid, p3.uuid], [r[0] for r in res])

    @snapshot_clickhouse_queries
    def test_person_properties_with_pushdowns(self):

        action1 = Action.objects.create(team=self.team, name="action1")
        ActionStep.objects.create(
            event="$autocapture", action=action1, url="https://posthog.com/feedback/123", url_matching=ActionStep.EXACT,
        )

        # satiesfies all conditions
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$autocapture",
            properties={"$current_url": "https://posthog.com/feedback/123"},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=2),
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p1",
            timestamp=datetime.now() - timedelta(days=1),
        )

        # doesn't satisfy action
        p2 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p2"], properties={"name": "test", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$autocapture",
            properties={"$current_url": "https://posthog.com/feedback/123"},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(weeks=3),
        )
        _create_event(
            team=self.team,
            event="$pageview",
            properties={},
            distinct_id="p2",
            timestamp=datetime.now() - timedelta(days=1),
        )

        # satisfies special condition (not pushed down person property in OR group)
        p3 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p3"], properties={"name": "special", "email": "test@posthog.com"}
        )
        _create_event(
            team=self.team,
            event="$autocapture",
            properties={"$current_url": "https://posthog.com/feedback/123"},
            distinct_id="p3",
            timestamp=datetime.now() - timedelta(days=2),
        )

        filter = Filter(
            data={
                "properties": {
                    "type": "AND",
                    "values": [
                        {
                            "type": "OR",
                            "values": [
                                {
                                    "key": "$pageview",
                                    "event_type": "events",
                                    "time_value": 1,
                                    "time_interval": "day",
                                    "value": "performed_event",
                                    "type": "behavioural",
                                },
                                {
                                    "key": "$pageview",
                                    "event_type": "events",
                                    "time_value": 2,
                                    "time_interval": "week",
                                    "value": "performed_event",
                                    "type": "behavioural",
                                },
                                {"key": "name", "value": "special", "type": "person"},  # this is NOT pushed down
                            ],
                        },
                        {
                            "type": "AND",
                            "values": [
                                {
                                    "key": action1.pk,
                                    "event_type": "actions",
                                    "time_value": 2,
                                    "time_interval": "week",
                                    "value": "performed_event_first_time",
                                    "type": "behavioural",
                                },
                                {"key": "email", "value": "test@posthog.com", "type": "person"},  # this is pushed down
                            ],
                        },
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        self.assertCountEqual([p1.uuid, p3.uuid], [r[0] for r in res])

    def test_person_materialized(self):
        materialize("person", "$sample_field")

        # satiesfies all conditions
        p1 = Person.objects.create(
            team_id=self.team.pk, distinct_ids=["p1"], properties={"name": "test", "$sample_field": "test@posthog.com"}
        )
        filter = Filter(
            data={
                "properties": {
                    "type": "OR",
                    "values": [
                        {
                            "key": "$pageview",
                            "event_type": "events",
                            "time_value": 1,
                            "time_interval": "week",
                            "value": "performed_event",
                            "type": "behavioural",
                        },
                        {"key": "$sample_field", "value": "test@posthog.com", "type": "person"},
                    ],
                },
            }
        )

        q, params = CohortQuery(filter=filter, team=self.team).get_query()
        res = sync_execute(q, params)

        self.assertEqual([p1.uuid], [r[0] for r in res])

import json
from typing import Any, Dict, Type

from django.db.models import OuterRef, QuerySet, Subquery
from django.db.models.query_utils import Q
from django.http import HttpResponse
from django.utils.text import slugify
from django.utils.timezone import now
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiResponse
from rest_framework import exceptions, request, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework_csv import renderers as csvrenderers
from sentry_sdk import capture_exception

from ee.clickhouse.queries.funnels import ClickhouseFunnelTimeToConvert, ClickhouseFunnelTrends
from ee.clickhouse.queries.funnels.utils import get_funnel_order_class
from ee.clickhouse.queries.paths.paths import ClickhousePaths
from ee.clickhouse.queries.retention.clickhouse_retention import ClickhouseRetention
from ee.clickhouse.queries.stickiness.clickhouse_stickiness import ClickhouseStickiness
from ee.clickhouse.queries.trends.clickhouse_trends import ClickhouseTrends
from posthog.api.documentation import extend_schema
from posthog.api.insight_serializers import (
    FunnelSerializer,
    FunnelStepsResultsSerializer,
    TrendResultsSerializer,
    TrendSerializer,
)
from posthog.api.routing import StructuredViewSetMixin
from posthog.api.shared import UserBasicSerializer
from posthog.api.tagged_item import TaggedItemSerializerMixin, TaggedItemViewSetMixin
from posthog.api.utils import format_paginated_url
from posthog.constants import (
    BREAKDOWN_VALUES_LIMIT,
    FROM_DASHBOARD,
    INSIGHT,
    INSIGHT_FUNNELS,
    INSIGHT_PATHS,
    INSIGHT_STICKINESS,
    PATHS_INCLUDE_EVENT_TYPES,
    TRENDS_STICKINESS,
    FunnelVizType,
)
from posthog.decorators import cached_function
from posthog.helpers.multi_property_breakdown import protect_old_clients_from_multi_property_default
from posthog.models import Filter, Insight, Team
from posthog.models.activity_logging.activity_log import (
    ActivityPage,
    Detail,
    changes_between,
    load_activity,
    log_activity,
)
from posthog.models.activity_logging.serializers import ActivityLogSerializer
from posthog.models.dashboard import Dashboard
from posthog.models.filters import RetentionFilter
from posthog.models.filters.path_filter import PathFilter
from posthog.models.filters.stickiness_filter import StickinessFilter
from posthog.models.insight import InsightViewed
from posthog.permissions import ProjectMembershipNecessaryPermissions, TeamMemberAccessPermission
from posthog.queries.util import get_earliest_timestamp
from posthog.settings import SITE_URL
from posthog.tasks.update_cache import update_dashboard_item_cache
from posthog.utils import (
    format_query_params_absolute_url,
    get_safe_cache,
    relative_date_parse,
    should_refresh,
    str_to_bool,
)


class InsightBasicSerializer(serializers.ModelSerializer):
    """
    Simplified serializer to speed response times when loading large amounts of objects.
    """

    class Meta:
        model = Insight
        fields = [
            "id",
            "short_id",
            "name",
            "filters",
            "dashboard",
            "color",
            "description",
            "last_refresh",
            "refreshing",
            "saved",
            "updated_at",
        ]
        read_only_fields = ("short_id", "updated_at")

    def create(self, validated_data: Dict, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["filters"] = instance.dashboard_filters()
        return representation


class InsightSerializer(TaggedItemSerializerMixin, InsightBasicSerializer):
    result = serializers.SerializerMethodField()
    last_refresh = serializers.SerializerMethodField()
    created_by = UserBasicSerializer(read_only=True)
    last_modified_by = UserBasicSerializer(read_only=True)
    effective_privilege_level = serializers.SerializerMethodField()

    class Meta:
        model = Insight
        fields = [
            "id",
            "short_id",
            "name",
            "derived_name",
            "filters",
            "filters_hash",
            "order",
            "deleted",
            "dashboard",
            "layouts",
            "color",
            "last_refresh",
            "refreshing",
            "result",
            "created_at",
            "created_by",
            "description",
            "updated_at",
            "tags",
            "favorited",
            "saved",
            "last_modified_at",
            "last_modified_by",
            "is_sample",
            "effective_restriction_level",
            "effective_privilege_level",
        ]
        read_only_fields = (
            "created_at",
            "created_by",
            "last_modified_at",
            "last_modified_by",
            "short_id",
            "updated_at",
            "is_sample",
            "effective_restriction_level",
            "effective_privilege_level",
        )

    def create(self, validated_data: Dict, *args: Any, **kwargs: Any) -> Insight:
        request = self.context["request"]
        team = Team.objects.get(id=self.context["team_id"])
        validated_data.pop("last_refresh", None)  # last_refresh sometimes gets sent if dashboard_item is duplicated
        tags = validated_data.pop("tags", None)  # tags are created separately as global tag relationships

        if not validated_data.get("dashboard", None):
            dashboard_item = Insight.objects.create(
                team=team, created_by=request.user, last_modified_by=request.user, **validated_data
            )
        elif validated_data["dashboard"].team == team:
            created_by = validated_data.pop("created_by", request.user)
            dashboard_item = Insight.objects.create(
                team=team, last_refresh=now(), created_by=created_by, last_modified_by=created_by, **validated_data
            )
        else:
            raise serializers.ValidationError("Dashboard not found")

        # Manual tag creation since this create method doesn't call super()
        self._attempt_set_tags(tags, dashboard_item)

        name_for_logged_activity = dashboard_item.name if len(dashboard_item.name) > 0 else dashboard_item.derived_name
        log_activity(
            organization_id=self.context["request"].user.current_organization_id,
            team_id=team.id,
            user=self.context["request"].user,
            item_id=dashboard_item.id,
            scope="Insight",
            activity="created",
            detail=Detail(name=name_for_logged_activity, short_id=dashboard_item.short_id),
        )
        return dashboard_item

    def update(self, instance: Insight, validated_data: Dict, **kwargs) -> Insight:
        try:
            before_update = Insight.objects.get(pk=instance.id)
        except Insight.DoesNotExist:
            before_update = None

        # Remove is_sample if it's set as user has altered the sample configuration
        validated_data["is_sample"] = False
        if validated_data.keys() & Insight.MATERIAL_INSIGHT_FIELDS:
            instance.last_modified_at = now()
            instance.last_modified_by = self.context["request"].user

        updated_insight = super().update(instance, validated_data)

        changes = changes_between("Insight", previous=before_update, current=updated_insight)

        name_for_logged_activity = (
            updated_insight.name if len(updated_insight.name) > 0 else updated_insight.derived_name
        )
        log_activity(
            organization_id=self.context["request"].user.current_organization_id,
            team_id=self.context["team_id"],
            user=self.context["request"].user,
            item_id=updated_insight.id,
            scope="Insight",
            activity="updated",
            detail=Detail(name=name_for_logged_activity, changes=changes, short_id=updated_insight.short_id),
        )

        return updated_insight

    def get_result(self, insight: Insight):
        if not insight.filters:
            return None
        if should_refresh(self.context["request"]):
            return update_dashboard_item_cache(insight, None)

        result = get_safe_cache(insight.filters_hash)
        if not result or result.get("task_id", None):
            return None
        # Data might not be defined if there is still cached results from before moving from 'results' to 'data'
        return result.get("result")

    def get_last_refresh(self, insight: Insight):
        if should_refresh(self.context["request"]):
            return now()

        result = self.get_result(insight)
        if result is not None:
            return insight.last_refresh
        if insight.last_refresh is not None:
            # Update last_refresh without updating "updated_at" (insight edit date)
            insight.last_refresh = None
            insight.save()
        return None

    def get_effective_privilege_level(self, insight: Insight) -> Dashboard.PrivilegeLevel:
        return insight.get_effective_privilege_level(self.context["request"].user.id)

    def to_representation(self, instance: Insight):
        representation = super().to_representation(instance)
        representation["filters"] = instance.dashboard_filters(dashboard=self.context.get("dashboard"))
        return representation


class InsightViewSet(TaggedItemViewSetMixin, StructuredViewSetMixin, viewsets.ModelViewSet):
    queryset = Insight.objects.all().prefetch_related(
        "dashboard", "dashboard__team", "dashboard__team__organization", "created_by"
    )
    serializer_class = InsightSerializer
    permission_classes = [IsAuthenticated, ProjectMembershipNecessaryPermissions, TeamMemberAccessPermission]
    renderer_classes = tuple(api_settings.DEFAULT_RENDERER_CLASSES) + (csvrenderers.CSVRenderer,)
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["short_id", "created_by"]
    include_in_docs = True

    def get_serializer_class(self) -> Type[serializers.BaseSerializer]:

        if (self.action == "list" or self.action == "retrieve") and str_to_bool(
            self.request.query_params.get("basic", "0"),
        ):
            return InsightBasicSerializer
        return super().get_serializer_class()

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()
        if self.action == "list":
            queryset = queryset.filter(deleted=False)
            queryset = self._filter_request(self.request, queryset)

        order = self.request.GET.get("order", None)
        if order:
            if order == "-my_last_viewed_at":
                queryset = self._annotate_with_my_last_viewed_at(queryset).order_by("-my_last_viewed_at")
            else:
                queryset = queryset.order_by(order)
        else:
            queryset = queryset.order_by("order")

        return queryset

    def _annotate_with_my_last_viewed_at(self, queryset: QuerySet) -> QuerySet:
        if self.request.user.is_authenticated:
            insight_viewed = InsightViewed.objects.filter(
                team=self.team, user=self.request.user, insight_id=OuterRef("id")
            )
            return queryset.annotate(my_last_viewed_at=Subquery(insight_viewed.values("last_viewed_at")[:1]))
        raise exceptions.NotAuthenticated()

    def _filter_request(self, request: request.Request, queryset: QuerySet) -> QuerySet:
        filters = request.GET.dict()

        for key in filters:
            if key == "saved":
                if str_to_bool(request.GET["saved"]):
                    queryset = queryset.filter(Q(saved=True) | Q(dashboard__isnull=False))
                else:
                    queryset = queryset.filter(Q(saved=False))

            elif key == "my_last_viewed":
                if str_to_bool(request.GET["my_last_viewed"]):
                    queryset = self._annotate_with_my_last_viewed_at(queryset).filter(my_last_viewed_at__isnull=False)
            elif key == "user":
                queryset = queryset.filter(created_by=request.user)
            elif key == "favorited":
                queryset = queryset.filter(Q(favorited=True))
            elif key == "date_from":
                queryset = queryset.filter(last_modified_at__gt=relative_date_parse(request.GET["date_from"]))
            elif key == "date_to":
                queryset = queryset.filter(last_modified_at__lt=relative_date_parse(request.GET["date_to"]))
            elif key == INSIGHT:
                queryset = queryset.filter(filters__insight=request.GET[INSIGHT])
            elif key == "search":
                queryset = queryset.filter(
                    Q(name__icontains=request.GET["search"]) | Q(derived_name__icontains=request.GET["search"])
                )
        return queryset

    @action(methods=["patch"], detail=False)
    def layouts(self, request, **kwargs):
        """Dashboard item layouts."""
        queryset = self.get_queryset()
        for data in request.data["items"]:
            queryset.filter(pk=data["id"]).update(layouts=data["layouts"])
        serializer = self.get_serializer(queryset.all(), many=True)
        return Response(serializer.data)

    # ******************************************
    # Calculated Insight Endpoints
    # /projects/:id/insights/trend
    # /projects/:id/insights/funnel
    # /projects/:id/insights/retention
    # /projects/:id/insights/path
    #
    # Request parameteres and caching are handled here and passed onto respective .queries classes
    # ******************************************

    # ******************************************
    # /projects/:id/insights/trend
    #
    # params:
    # - from_dashboard: (string) determines trend is being retrieved from dashboard item to update dashboard_item metadata
    # - shown_as: (string: Volume, Stickiness) specifies the trend aggregation type
    # - **shared filter types
    # ******************************************
    @extend_schema(
        request=TrendSerializer,
        methods=["POST"],
        tags=["trend"],
        operation_id="Trends",
        responses=TrendResultsSerializer,
    )
    @action(methods=["GET", "POST"], detail=False)
    def trend(self, request: request.Request, *args: Any, **kwargs: Any):
        try:
            serializer = TrendSerializer(request=request)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            capture_exception(e)

        result = self.calculate_trends(request)
        filter = Filter(request=request, team=self.team)
        next = (
            format_paginated_url(request, filter.offset, BREAKDOWN_VALUES_LIMIT)
            if len(result["result"]) >= BREAKDOWN_VALUES_LIMIT
            else None
        )
        if self.request.accepted_renderer.format == "csv":
            csvexport = []
            for item in result["result"]:
                line = {"series": item["label"]}
                for index, data in enumerate(item["data"]):
                    line[item["labels"][index]] = data
                csvexport.append(line)
            renderer = csvrenderers.CSVRenderer()
            renderer.header = csvexport[0].keys()
            export = renderer.render(csvexport)
            if request.GET.get("export_insight_id"):
                export = "{}/insights/{}/\n".format(SITE_URL, request.GET["export_insight_id"]).encode() + export

            response = HttpResponse(export)
            response[
                "Content-Disposition"
            ] = 'attachment; filename="{name} ({date_from} {date_to}) from PostHog.csv"'.format(
                name=slugify(request.GET.get("export_name", "export")),
                date_from=filter.date_from.strftime("%Y-%m-%d -") if filter.date_from else "up until",
                date_to=filter.date_to.strftime("%Y-%m-%d"),
            )
            return response
        return Response({**result, "next": next})

    @cached_function
    def calculate_trends(self, request: request.Request) -> Dict[str, Any]:
        team = self.team
        filter = Filter(request=request, team=self.team)

        if filter.insight == INSIGHT_STICKINESS or filter.shown_as == TRENDS_STICKINESS:
            stickiness_filter = StickinessFilter(
                request=request, team=team, get_earliest_timestamp=get_earliest_timestamp
            )
            result = ClickhouseStickiness().run(stickiness_filter, team)
        else:
            trends_query = ClickhouseTrends()
            result = trends_query.run(filter, team)

        self._refresh_dashboard(request=request)
        return {"result": result}

    # ******************************************
    # /projects/:id/insights/funnel
    # The funnel endpoint is asynchronously processed. When a request is received, the endpoint will
    # call an async task with an id that can be continually polled for 3 minutes.
    #
    # params:
    # - refresh: (dict) specifies cache to force refresh or poll
    # - from_dashboard: (dict) determines funnel is being retrieved from dashboard item to update dashboard_item metadata
    # - **shared filter types
    # ******************************************
    @extend_schema(
        request=FunnelSerializer,
        responses=OpenApiResponse(
            response=FunnelStepsResultsSerializer,
            description="Note, if funnel_viz_type is set the response will be different.",
        ),
        methods=["POST"],
        tags=["funnel"],
        operation_id="Funnels",
    )
    @action(methods=["GET", "POST"], detail=False)
    def funnel(self, request: request.Request, *args: Any, **kwargs: Any) -> Response:
        try:
            serializer = FunnelSerializer(request=request)
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            capture_exception(e)

        funnel = self.calculate_funnel(request)

        funnel["result"] = protect_old_clients_from_multi_property_default(request.data, funnel["result"])

        return Response(funnel)

    @cached_function
    def calculate_funnel(self, request: request.Request) -> Dict[str, Any]:
        team = self.team
        filter = Filter(request=request, data={"insight": INSIGHT_FUNNELS}, team=self.team)

        if filter.funnel_viz_type == FunnelVizType.TRENDS:
            return {"result": ClickhouseFunnelTrends(team=team, filter=filter).run()}
        elif filter.funnel_viz_type == FunnelVizType.TIME_TO_CONVERT:
            return {"result": ClickhouseFunnelTimeToConvert(team=team, filter=filter).run()}
        else:
            funnel_order_class = get_funnel_order_class(filter)
            return {"result": funnel_order_class(team=team, filter=filter).run()}

    # ******************************************
    # /projects/:id/insights/retention
    # params:
    # - start_entity: (dict) specifies id and type of the entity to focus retention on
    # - **shared filter types
    # ******************************************
    @action(methods=["GET"], detail=False)
    def retention(self, request: request.Request, *args: Any, **kwargs: Any) -> Response:
        result = self.calculate_retention(request)
        return Response(result)

    @cached_function
    def calculate_retention(self, request: request.Request) -> Dict[str, Any]:
        team = self.team
        data = {}
        if not request.GET.get("date_from"):
            data.update({"date_from": "-11d"})
        filter = RetentionFilter(data=data, request=request, team=self.team)
        base_uri = request.build_absolute_uri("/")
        result = ClickhouseRetention(base_uri=base_uri).run(filter, team)
        return {"result": result}

    # ******************************************
    # /projects/:id/insights/path
    # params:
    # - start: (string) specifies the name of the starting property or element
    # - request_type: (string: $pageview, $autocapture, $screen, custom_event) specifies the path type
    # - **shared filter types
    # ******************************************
    @action(methods=["GET", "POST"], detail=False)
    def path(self, request: request.Request, *args: Any, **kwargs: Any) -> Response:
        result = self.calculate_path(request)
        return Response(result)

    @cached_function
    def calculate_path(self, request: request.Request) -> Dict[str, Any]:
        team = self.team
        filter = PathFilter(request=request, data={"insight": INSIGHT_PATHS}, team=self.team)

        funnel_filter = None
        funnel_filter_data = request.GET.get("funnel_filter") or request.data.get("funnel_filter")
        if funnel_filter_data:
            if isinstance(funnel_filter_data, str):
                funnel_filter_data = json.loads(funnel_filter_data)
            funnel_filter = Filter(data={"insight": INSIGHT_FUNNELS, **funnel_filter_data}, team=self.team)

        #  backwards compatibility
        if filter.path_type:
            filter = filter.with_data({PATHS_INCLUDE_EVENT_TYPES: [filter.path_type]})
        resp = ClickhousePaths(filter=filter, team=team, funnel_filter=funnel_filter).run()

        return {"result": resp}

    # Checks if a dashboard id has been set and if so, update the refresh date
    def _refresh_dashboard(self, request) -> None:
        dashboard_id = request.GET.get(FROM_DASHBOARD, None)
        if dashboard_id:
            Insight.objects.filter(pk=dashboard_id).update(last_refresh=now())

    # ******************************************
    # /projects/:id/insights/:short_id/viewed
    # Creates or updates an InsightViewed object for the user/insight combo
    # ******************************************
    @action(methods=["POST"], detail=True)
    def viewed(self, request: request.Request, *args: Any, **kwargs: Any) -> Response:
        InsightViewed.objects.update_or_create(
            team=self.team, user=request.user, insight=self.get_object(), defaults={"last_viewed_at": now()}
        )
        return Response(status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance: Insight = self.get_object()
        instance_id = instance.id
        instance_short_id = instance.short_id

        instance.delete()

        name_for_logged_activity = instance.name if len(instance.name) > 0 else instance.derived_name
        log_activity(
            organization_id=self.organization.id,
            team_id=self.team_id,
            user=request.user,
            item_id=instance_id,
            scope="Insight",
            activity="deleted",
            detail=Detail(name=name_for_logged_activity, short_id=instance_short_id),
        )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=["GET"], url_path="activity", detail=False)
    def all_activity(self, request: request.Request, **kwargs):
        limit = int(request.query_params.get("limit", "10"))
        page = int(request.query_params.get("page", "1"))
        activity_page = load_activity(scope="Insight", team_id=self.team_id)
        return self._return_activity_page(activity_page, limit, page, request)

    @action(methods=["GET"], detail=True)
    def activity(self, request: request.Request, **kwargs):
        limit = int(request.query_params.get("limit", "10"))
        page = int(request.query_params.get("page", "1"))

        item_id = kwargs["pk"]
        if not Insight.objects.filter(id=item_id, team_id=self.team_id).exists():
            return Response("", status=status.HTTP_404_NOT_FOUND)

        activity_page = load_activity(scope="Insight", team_id=self.team_id, item_id=item_id, limit=limit, page=page)
        return self._return_activity_page(activity_page, limit, page, request)

    @staticmethod
    def _return_activity_page(activity_page: ActivityPage, limit: int, page: int, request: request.Request) -> Response:
        return Response(
            {
                "results": ActivityLogSerializer(activity_page.results, many=True,).data,
                "next": format_query_params_absolute_url(request, page + 1, limit, offset_alias="page")
                if activity_page.has_next
                else None,
                "previous": format_query_params_absolute_url(request, page - 1, limit, offset_alias="page")
                if activity_page.has_previous
                else None,
                "total_count": activity_page.total_count,
            },
            status=status.HTTP_200_OK,
        )


class LegacyInsightViewSet(InsightViewSet):
    legacy_team_compatibility = True

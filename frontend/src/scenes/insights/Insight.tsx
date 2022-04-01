import './Insight.scss'
import React, { useEffect } from 'react'
import { useActions, useMountedLogic, useValues, BindLogic } from 'kea'
import { Card } from 'antd'
import { FunnelTab, PathTab, RetentionTab, TrendTab } from './InsightTabs'
import { insightSceneLogic } from 'scenes/insights/insightSceneLogic'
import { insightLogic } from './insightLogic'
import { insightCommandLogic } from './insightCommandLogic'
import { ItemMode, InsightType, AvailableFeature, InsightShortId, ChartDisplayType } from '~/types'
import { NPSPrompt } from 'lib/experimental/NPSPrompt'
import { SaveCohortModal } from 'scenes/trends/SaveCohortModal'
import { personsModalLogic } from 'scenes/trends/personsModalLogic'
import { InsightsNav } from './InsightsNav'
import { SaveToDashboard } from 'lib/components/SaveToDashboard/SaveToDashboard'
import { InsightContainer } from 'scenes/insights/InsightContainer'
import { EditableField } from 'lib/components/EditableField/EditableField'
import { ObjectTags } from 'lib/components/ObjectTags/ObjectTags'
import { InsightSaveButton } from './InsightSaveButton'
import { userLogic } from 'scenes/userLogic'
import { FeedbackCallCTA } from 'lib/experimental/FeedbackCallCTA'
import { PageHeader } from 'lib/components/PageHeader'
import { LastModified } from 'lib/components/InsightCard/LastModified'
import { IconLock } from 'lib/components/icons'
import { summarizeInsightFilters } from './utils'
import { groupsModel } from '~/models/groupsModel'
import { cohortsModel } from '~/models/cohortsModel'
import { mathsLogic } from 'scenes/trends/mathsLogic'
import { InsightSkeleton } from 'scenes/insights/InsightSkeleton'
import { LemonButton } from 'lib/components/LemonButton'
import useBreakpoint from 'antd/lib/grid/hooks/useBreakpoint'

const LIVE_MODE_INTERVAL_MS = 30000

export function Insight({ insightId }: { insightId: InsightShortId | 'new' }): JSX.Element {
    const { insightMode } = useValues(insightSceneLogic)
    const { setInsightMode } = useActions(insightSceneLogic)

    const logic = insightLogic({ dashboardItemId: insightId || 'new' })
    const {
        insightProps,
        insightLoading,
        filtersKnown,
        filters,
        canEditInsight,
        activeView,
        insight,
        insightChanged,
        tagLoading,
        sourceDashboardId,
    } = useValues(logic)
    useMountedLogic(insightCommandLogic(insightProps))
    const { saveInsight, setInsightMetadata, saveAs, cancelChanges, loadResults } = useActions(logic)
    const { hasAvailableFeature } = useValues(userLogic)
    const { cohortModalVisible } = useValues(personsModalLogic)
    const { saveCohortWithUrl, setCohortModalVisible } = useActions(personsModalLogic)
    const { aggregationLabel } = useValues(groupsModel)
    const { cohortsById } = useValues(cohortsModel)
    const { mathDefinitions } = useValues(mathsLogic)
    const screens = useBreakpoint()

    const isSmallScreen = !screens.xl

    // Whether to display the control tab on the side instead of on top
    const verticalLayout = !isSmallScreen && activeView === InsightType.FUNNELS

    useEffect(() => {
        if (insight.filters?.display === ChartDisplayType.Hedgehogger) {
            loadResults(true)
            const timeout = setInterval(() => {
                loadResults(true)
            }, LIVE_MODE_INTERVAL_MS)
            return () => clearInterval(timeout)
        }
    }, [insight.filters?.display])

    // Show the skeleton if loading an insight for which we only know the id
    // This helps with the UX flickering and showing placeholder "name" text.
    if (insightId !== 'new' && insightLoading && !filtersKnown) {
        return <InsightSkeleton />
    }

    /* These are insight specific filters. They each have insight specific logics */
    const insightTab = {
        [`${InsightType.TRENDS}`]: <TrendTab view={InsightType.TRENDS} />,
        [`${InsightType.STICKINESS}`]: <TrendTab view={InsightType.STICKINESS} />,
        [`${InsightType.LIFECYCLE}`]: <TrendTab view={InsightType.LIFECYCLE} />,
        [`${InsightType.FUNNELS}`]: <FunnelTab />,
        [`${InsightType.RETENTION}`]: <RetentionTab />,
        [`${InsightType.PATHS}`]: <PathTab />,
    }[activeView]

    const insightScene = (
        <div className="insights-page">
            <PageHeader
                title={
                    <EditableField
                        name="name"
                        value={insight.name || ''}
                        placeholder={summarizeInsightFilters(filters, aggregationLabel, cohortsById, mathDefinitions)}
                        onSave={(value) => setInsightMetadata({ name: value })}
                        maxLength={400} // Sync with Insight model
                        mode={!canEditInsight ? 'view' : undefined}
                        data-attr="insight-name"
                        notice={
                            !canEditInsight
                                ? {
                                      icon: <IconLock />,
                                      tooltip:
                                          "You don't have edit permissions in the dashboard this insight belongs to. Ask a dashboard collaborator with edit access to add you.",
                                  }
                                : undefined
                        }
                    />
                }
                buttons={
                    <div className="insights-tab-actions">
                        {insightMode === ItemMode.Edit && insight.saved && (
                            <LemonButton type="secondary" onClick={cancelChanges}>
                                Cancel
                            </LemonButton>
                        )}
                        {insightMode === ItemMode.View && insight.short_id && (
                            <SaveToDashboard insight={insight} sourceDashboardId={sourceDashboardId} />
                        )}
                        {insightMode === ItemMode.View ? (
                            canEditInsight && (
                                <LemonButton
                                    type="primary"
                                    style={{ marginLeft: 8 }}
                                    onClick={() => setInsightMode(ItemMode.Edit, null)}
                                    data-attr="insight-edit-button"
                                >
                                    Edit
                                </LemonButton>
                            )
                        ) : (
                            <InsightSaveButton
                                saveAs={saveAs}
                                saveInsight={saveInsight}
                                isSaved={insight.saved}
                                addingToDashboard={!!insight.dashboard && !insight.id}
                                insightChanged={insightChanged}
                            />
                        )}
                    </div>
                }
                caption={
                    <>
                        {!!(canEditInsight || insight.description) && (
                            <EditableField
                                multiline
                                name="description"
                                value={insight.description || ''}
                                placeholder="Description (optional)"
                                onSave={(value) => setInsightMetadata({ description: value })}
                                maxLength={400} // Sync with Insight model
                                mode={!canEditInsight ? 'view' : undefined}
                                data-attr="insight-description"
                                compactButtons
                                paywall={!hasAvailableFeature(AvailableFeature.DASHBOARD_COLLABORATION)}
                                notice={
                                    !canEditInsight
                                        ? {
                                              icon: <IconLock />,
                                              tooltip:
                                                  "You don't have edit permissions in the dashboard this insight belongs to. Ask a dashboard collaborator with edit access to add you.",
                                          }
                                        : undefined
                                }
                            />
                        )}
                        {hasAvailableFeature(AvailableFeature.TAGGING) &&
                            (canEditInsight ? (
                                <ObjectTags
                                    tags={insight.tags ?? []}
                                    onChange={(_, tags) => setInsightMetadata({ tags: tags ?? [] })}
                                    saving={tagLoading}
                                    tagsAvailable={[]}
                                    className="insight-metadata-tags"
                                    data-attr="insight-tags"
                                />
                            ) : insight.tags?.length ? (
                                <ObjectTags
                                    tags={insight.tags}
                                    saving={tagLoading}
                                    className="insight-metadata-tags"
                                    data-attr="insight-tags"
                                    staticOnly
                                />
                            ) : null)}
                        <LastModified at={insight.last_modified_at} by={insight.last_modified_by} />
                    </>
                }
            />
            {insightMode === ItemMode.View ? (
                <InsightContainer />
            ) : (
                <>
                    <InsightsNav />

                    <div
                        style={{
                            display: 'flex',
                            flexDirection: verticalLayout ? 'row' : 'column',
                            marginBottom: verticalLayout ? 64 : 0,
                        }}
                    >
                        <div
                            style={{
                                width: verticalLayout ? 'min(32rem, 50%)' : 'unset',
                                marginRight: verticalLayout ? '1rem' : 0,
                            }}
                        >
                            {verticalLayout ? (
                                insightTab
                            ) : (
                                <Card className="insight-controls">
                                    <div className="tabs-inner">
                                        {/* These are insight specific filters. They each have insight specific logics */}
                                        {insightTab}
                                    </div>
                                </Card>
                            )}
                        </div>
                        <div
                            style={{
                                flexGrow: 1,
                                width: verticalLayout ? 'calc(100% - min(32rem, 50%) - 1rem)' : 'unset',
                            }}
                        >
                            <InsightContainer />
                        </div>
                    </div>
                    <NPSPrompt />
                    <FeedbackCallCTA />
                </>
            )}

            <SaveCohortModal
                visible={cohortModalVisible}
                onOk={(title: string) => {
                    saveCohortWithUrl(title)
                    setCohortModalVisible(false)
                }}
                onCancel={() => setCohortModalVisible(false)}
            />
        </div>
    )

    return (
        <BindLogic logic={insightLogic} props={insightProps}>
            {insightScene}
        </BindLogic>
    )
}

import { useActions, useValues } from 'kea'
import { useEffect } from 'react'
import { ChartDisplayType } from '~/types'
import { insightLogic } from '../insightLogic'

const LIVE_MODE_INTERVAL_MS = 30000

/** Reload results periodically when the insight is in Live mode. Only works if insightLogic is bound. */
export function useLiveMode(): void {
    const { insight } = useValues(insightLogic)
    const { loadResults } = useActions(insightLogic)

    useEffect(() => {
        if (insight.filters?.display === ChartDisplayType.WorldMap) {
            loadResults(true)
            const timeout = setInterval(() => {
                loadResults(true)
            }, LIVE_MODE_INTERVAL_MS)
            return () => clearInterval(timeout)
        }
    }, [insight.filters?.display])
}

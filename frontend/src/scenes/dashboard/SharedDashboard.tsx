import React from 'react'
import { initKea } from '~/initKea'
import { Dashboard } from './Dashboard'
import { Col, Row } from 'antd'
import { loadPostHogJS } from '~/loadPostHogJS'
import { FriendlyLogo } from '~/toolbar/assets/FriendlyLogo'
import '~/styles'
import './DashboardItems.scss'
import { DashboardPlacement } from '~/types'
import { createRoot } from 'react-dom/client'

loadPostHogJS()
initKea()

const dashboard = (window as any).__SHARED_DASHBOARD__
const isEmbedded = window.location.search.includes('embedded')

const root = document.getElementById('root')
if (root) {
    createRoot(root).render(
        <div style={{ minHeight: '100vh', top: 0, padding: !isEmbedded ? '1rem' : '0.5rem 1rem' }}>
            {!isEmbedded ? (
                <Row align="middle">
                    <Col sm={7} xs={24}>
                        <a href="https://posthog.com" target="_blank" rel="noopener noreferrer">
                            <FriendlyLogo style={{ fontSize: '1.125rem' }} />
                        </a>
                    </Col>
                    <Col sm={10} xs={24} style={{ textAlign: 'center' }}>
                        <>
                            <h1 style={{ marginBottom: '0.25rem', fontWeight: 600 }} data-attr="dashboard-item-title">
                                {dashboard.name}
                            </h1>
                            <span>{dashboard.description}</span>
                        </>
                    </Col>
                    <Col sm={7} xs={0} style={{ textAlign: 'right' }}>
                        <span style={{ display: 'inline-block' }}>{dashboard.team_name}</span>
                    </Col>
                </Row>
            ) : (
                <a
                    href="https://posthog.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ display: 'block', marginBottom: '-3rem' }}
                >
                    <FriendlyLogo style={{ fontSize: '1.125rem' }} />
                </a>
            )}

            <Dashboard id={dashboard.id} shareToken={dashboard.share_token} placement={DashboardPlacement.Public} />

            <div style={{ textAlign: 'center', paddingBottom: '1rem' }}>
                Made with{' '}
                <a
                    href="https://posthog.com?utm_medium=in-product&utm_campaign=shared-dashboard"
                    target="_blank"
                    rel="noopener"
                >
                    PostHog – open-source product analytics
                </a>
            </div>
        </div>
    )
} else {
    console.error('Attempted, but could not render shared dashboard because <div id="root" /> is not found.')
}

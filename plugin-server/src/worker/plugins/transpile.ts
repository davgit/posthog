import { transform } from '@babel/standalone'

export function transpileFrontend(rawCode: string): string {
    const { code } = transform(rawCode, {
        envName: 'production',
        code: true,
        babelrc: false,
        configFile: false,
        filename: 'frontend.tsx',
        presets: [
            ['typescript', { isTSX: true, allExtensions: true }],
            ['env', { targets: { esmodules: true } }],
        ],
    })
    if (!code) {
        throw new Error('Could not transpile frontend.tsx')
    }
    return `"use strict";\nexport function getFrontendPluginExports (require) { let exports = {}; ${code}; return exports; }`
}
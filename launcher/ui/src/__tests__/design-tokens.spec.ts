import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const tokensCss = readFileSync(
  resolve(__dirname, '../design/tokens.css'),
  'utf-8',
)

describe('M3 design tokens', () => {
  it('defines M3 dark surface colors', () => {
    expect(tokensCss).toContain('--md-sys-color-background')
    expect(tokensCss).toContain('--md-sys-color-surface')
    expect(tokensCss).toContain('--md-sys-color-surface-variant')
    expect(tokensCss).toContain('--md-sys-color-surface-container-high')
  })

  it('defines M3 on-surface text colors', () => {
    expect(tokensCss).toContain('--md-sys-color-on-surface')
    expect(tokensCss).toContain('--md-sys-color-on-surface-variant')
  })

  it('defines brand primary color (xiaohongshu red)', () => {
    expect(tokensCss).toContain('--md-sys-color-primary')
    expect(tokensCss).toContain('--md-sys-color-on-primary')
    expect(tokensCss).toContain('--md-sys-color-primary-container')
  })

  it('defines semantic state colors', () => {
    expect(tokensCss).toContain('--md-sys-color-success')
    expect(tokensCss).toContain('--md-sys-color-on-success')
    expect(tokensCss).toContain('--md-sys-color-error')
    expect(tokensCss).toContain('--md-sys-color-on-error')
    expect(tokensCss).toContain('--md-sys-color-warning')
    expect(tokensCss).toContain('--md-sys-color-on-warning')
  })

  it('defines M3 elevation shadows', () => {
    expect(tokensCss).toContain('--md-sys-elevation-1')
    expect(tokensCss).toContain('--md-sys-elevation-2')
  })

  it('defines M3 type scale', () => {
    expect(tokensCss).toContain('--md-sys-typescale-headline-medium')
    expect(tokensCss).toContain('--md-sys-typescale-title-large')
    expect(tokensCss).toContain('--md-sys-typescale-title-medium')
    expect(tokensCss).toContain('--md-sys-typescale-body-large')
    expect(tokensCss).toContain('--md-sys-typescale-body-medium')
    expect(tokensCss).toContain('--md-sys-typescale-label-large')
    expect(tokensCss).toContain('--md-sys-typescale-label-medium')
  })

  it('defines M3 spacing on 4dp grid', () => {
    expect(tokensCss).toContain('--md-sys-spacing-1')
    expect(tokensCss).toContain('--md-sys-spacing-2')
    expect(tokensCss).toContain('--md-sys-spacing-4')
    expect(tokensCss).toContain('--md-sys-spacing-8')
  })

  it('defines M3 shape corners', () => {
    expect(tokensCss).toContain('--md-sys-shape-corner-small')
    expect(tokensCss).toContain('--md-sys-shape-corner-medium')
    expect(tokensCss).toContain('--md-sys-shape-corner-large')
  })
})

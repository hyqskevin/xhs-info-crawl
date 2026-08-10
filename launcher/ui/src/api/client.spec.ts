import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fetchStatus,
  restartService,
  stopAll,
  testOpencli,
  getOpencliDownloadUrl,
  getOcrStatus,
  installOcr,
  getOcrInstallProgress,
  testOcr,
  getLogsTail,
  setBaseUrl,
} from './client'

describe('launcher api client', () => {
  const originalFetch = globalThis.fetch

  beforeEach(() => {
    setBaseUrl('http://127.0.0.1:9001')
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('fetchStatus calls GET /status', async () => {
    const mockData = { api: { state: 'running', pid: 1 }, worker: { state: 'running', pid: 2 }, beat: { state: 'running', pid: 3 } }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as Response)

    const result = await fetchStatus()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/status')
    expect(result).toEqual(mockData)
  })

  it('restartService calls POST /service/{name}/restart', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response)

    const result = await restartService('api')
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/service/api/restart', { method: 'POST' })
    expect(result).toEqual({ ok: true })
  })

  it('stopAll calls POST /service/all/stop', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response)

    await stopAll()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/service/all/stop', { method: 'POST' })
  })

  it('testOpencli calls GET /opencli/test', async () => {
    const mockData = { ok: true, version: '1.8.6', reason: '', message: '连接正常' }
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as Response)

    const result = await testOpencli()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/opencli/test')
    expect(result).toEqual(mockData)
  })

  it('getOpencliDownloadUrl calls GET /opencli/download-url', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ url: 'https://opencli.info/download' }),
    } as Response)

    const result = await getOpencliDownloadUrl()
    expect(result).toEqual({ url: 'https://opencli.info/download' })
  })

  it('getOcrStatus calls GET /ocr/status', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'not_installed', version: '' }),
    } as Response)

    const result = await getOcrStatus()
    expect(result).toEqual({ status: 'not_installed', version: '' })
  })

  it('installOcr calls POST /ocr/install', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, message: '安装已启动' }),
    } as Response)

    const result = await installOcr()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/ocr/install', { method: 'POST' })
    expect(result).toEqual({ ok: true, message: '安装已启动' })
  })

  it('getOcrInstallProgress calls GET /ocr/install-progress', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ active: false, percent: 0, message: '' }),
    } as Response)

    const result = await getOcrInstallProgress()
    expect(result).toEqual({ active: false, percent: 0, message: '' })
  })

  it('testOcr calls POST /ocr/test', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, text: '测试文字', latency_ms: 123 }),
    } as Response)

    const result = await testOcr()
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/ocr/test', { method: 'POST' })
    expect(result).toEqual({ ok: true, text: '测试文字', latency_ms: 123 })
  })

  it('getLogsTail calls GET /logs/tail with lines param', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ lines: ['line1', 'line2'] }),
    } as Response)

    const result = await getLogsTail(50)
    expect(globalThis.fetch).toHaveBeenCalledWith('http://127.0.0.1:9001/logs/tail?lines=50')
    expect(result).toEqual({ lines: ['line1', 'line2'] })
  })

  it('throws on fetch error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network error'))
    await expect(fetchStatus()).rejects.toThrow('network error')
  })
})

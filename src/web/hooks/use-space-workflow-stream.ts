import { useEffect, useMemo, useRef, useState } from 'react'
import type {
  SpaceWorkflowBootstrapPayload,
  SpaceWorkflowSourceCardPayload,
} from '@/types/kernel'
import {
  parseSpaceWorkflowBootstrapEvent,
  parseSpaceWorkflowSourceCardEvent,
  parseWorkflowStreamErrorEvent,
} from '@/hooks/workflow-stream-parser'

const MAX_FAILURES_BEFORE_FALLBACK = 3
const BASE_RECONNECT_DELAY_MS = 1000
const MAX_RECONNECT_DELAY_MS = 12000

function computeReconnectDelay(attempt: number): number {
  const jitter = Math.floor(Math.random() * 250)
  const delay = BASE_RECONNECT_DELAY_MS * 2 ** Math.max(attempt - 1, 0)
  return Math.min(delay + jitter, MAX_RECONNECT_DELAY_MS)
}

interface UseSpaceWorkflowStreamOptions {
  spaceId: string
  sourceIds: string[]
  enabled: boolean
  onBootstrap?: (payload: SpaceWorkflowBootstrapPayload) => void
  onSourceCardStatus?: (payload: SpaceWorkflowSourceCardPayload) => void
}

interface UseSpaceWorkflowStreamResult {
  isConnected: boolean
  isFallbackActive: boolean
  lastError: string | null
}

export function useSpaceWorkflowStream({
  spaceId,
  sourceIds,
  enabled,
  onBootstrap,
  onSourceCardStatus,
}: UseSpaceWorkflowStreamOptions): UseSpaceWorkflowStreamResult {
  const [isConnected, setIsConnected] = useState(false)
  const [isFallbackActive, setIsFallbackActive] = useState(false)
  const [lastError, setLastError] = useState<string | null>(null)
  const reconnectTimerRef = useRef<number | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const closeRequestedRef = useRef(false)
  const consecutiveFailureCountRef = useRef(0)
  const onBootstrapRef = useRef(onBootstrap)
  const onSourceCardStatusRef = useRef(onSourceCardStatus)

  useEffect(() => {
    onBootstrapRef.current = onBootstrap
  }, [onBootstrap])

  useEffect(() => {
    onSourceCardStatusRef.current = onSourceCardStatus
  }, [onSourceCardStatus])

  const sourceIdsKey = useMemo(() => sourceIds.join(','), [sourceIds])
  const parsedSourceIds = useMemo(
    () => (sourceIdsKey.length > 0 ? sourceIdsKey.split(',') : []),
    [sourceIdsKey],
  )

  useEffect(() => {
    closeRequestedRef.current = false

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
    }

    const closeStream = () => {
      if (eventSourceRef.current !== null) {
        eventSourceRef.current.close()
        eventSourceRef.current = null
      }
      setIsConnected(false)
    }

    const scheduleReconnect = () => {
      if (closeRequestedRef.current || !enabled) {
        return
      }
      const delay = computeReconnectDelay(consecutiveFailureCountRef.current)
      clearReconnectTimer()
      reconnectTimerRef.current = window.setTimeout(() => {
        connect()
      }, delay)
    }

    const connect = () => {
      if (closeRequestedRef.current || !enabled) {
        return
      }
      if (typeof EventSource === 'undefined') {
        setIsFallbackActive(true)
        setLastError('EventSource is unavailable in this browser runtime.')
        return
      }

      const params = new URLSearchParams()
      if (parsedSourceIds.length > 0) {
        params.set('source_ids', parsedSourceIds.join(','))
      }
      const streamUrl =
        params.toString().length > 0
          ? `/api/research-spaces/${spaceId}/workflow-stream?${params.toString()}`
          : `/api/research-spaces/${spaceId}/workflow-stream`
      const stream = new EventSource(streamUrl)
      eventSourceRef.current = stream

      stream.onopen = () => {
        consecutiveFailureCountRef.current = 0
        setIsConnected(true)
        setIsFallbackActive(false)
        setLastError(null)
      }

      stream.onerror = () => {
        closeStream()
        consecutiveFailureCountRef.current += 1
        if (consecutiveFailureCountRef.current >= MAX_FAILURES_BEFORE_FALLBACK) {
          setIsFallbackActive(true)
        }
        scheduleReconnect()
      }

      stream.addEventListener('bootstrap', (event) => {
        if (!(event instanceof MessageEvent) || typeof event.data !== 'string') {
          return
        }
        const payload = parseSpaceWorkflowBootstrapEvent(event.data)
        if (payload !== null) {
          onBootstrapRef.current?.(payload)
        }
      })

      stream.addEventListener('source_card_status', (event) => {
        if (!(event instanceof MessageEvent) || typeof event.data !== 'string') {
          return
        }
        const payload = parseSpaceWorkflowSourceCardEvent(event.data)
        if (payload !== null) {
          onSourceCardStatusRef.current?.(payload)
        }
      })

      stream.addEventListener('error', (event) => {
        if (!(event instanceof MessageEvent) || typeof event.data !== 'string') {
          return
        }
        const errorMessage = parseWorkflowStreamErrorEvent(event.data)
        if (errorMessage !== null) {
          setLastError(errorMessage)
        }
      })
    }

    if (enabled) {
      connect()
    } else {
      setIsFallbackActive(false)
      setIsConnected(false)
      setLastError(null)
      consecutiveFailureCountRef.current = 0
    }

    return () => {
      closeRequestedRef.current = true
      clearReconnectTimer()
      closeStream()
    }
  }, [enabled, parsedSourceIds, spaceId, sourceIdsKey])

  return {
    isConnected,
    isFallbackActive,
    lastError,
  }
}

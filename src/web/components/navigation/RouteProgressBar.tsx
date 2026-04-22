'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { usePathname } from 'next/navigation'
import { Loader2 } from 'lucide-react'

const START_DELAY_MS = 120
const COMPLETE_HIDE_DELAY_MS = 180
const MAX_IN_FLIGHT_PROGRESS = 92
const INITIAL_PROGRESS = 14
const MIN_PROGRESS_STEP = 2
const PROGRESS_TICK_MS = 160

function isModifiedClick(event: MouseEvent): boolean {
  return event.metaKey || event.ctrlKey || event.shiftKey || event.altKey
}

function isInternalNavigationAnchor(anchor: HTMLAnchorElement): boolean {
  if (anchor.target === '_blank' || anchor.hasAttribute('download')) {
    return false
  }

  const href = anchor.getAttribute('href')
  if (!href || href.startsWith('#')) {
    return false
  }

  try {
    const url = new URL(anchor.href, window.location.href)
    if (url.origin !== window.location.origin) {
      return false
    }

    const currentPathWithQuery = `${window.location.pathname}${window.location.search}`
    const targetPathWithQuery = `${url.pathname}${url.search}`
    return currentPathWithQuery !== targetPathWithQuery
  } catch {
    return false
  }
}

export function RouteProgressBar() {
  const pathname = usePathname()

  const [progress, setProgress] = useState(0)
  const [loading, setLoading] = useState(false)

  const previousPathRef = useRef(pathname)
  const loadingRef = useRef(false)
  const progressRef = useRef(0)
  const startDelayTimerRef = useRef<number | null>(null)
  const progressTickTimerRef = useRef<number | null>(null)

  const clearStartDelayTimer = useCallback(() => {
    if (startDelayTimerRef.current !== null) {
      window.clearTimeout(startDelayTimerRef.current)
      startDelayTimerRef.current = null
    }
  }, [])

  const clearProgressTickTimer = useCallback(() => {
    if (progressTickTimerRef.current !== null) {
      window.clearInterval(progressTickTimerRef.current)
      progressTickTimerRef.current = null
    }
  }, [])

  const startTransition = useCallback(() => {
    clearStartDelayTimer()
    clearProgressTickTimer()

    startDelayTimerRef.current = window.setTimeout(() => {
      loadingRef.current = true
      progressRef.current = INITIAL_PROGRESS
      setLoading(true)
      setProgress(INITIAL_PROGRESS)
      progressTickTimerRef.current = window.setInterval(() => {
        setProgress((previous) => {
          if (previous >= MAX_IN_FLIGHT_PROGRESS) {
            return previous
          }
          const remaining = MAX_IN_FLIGHT_PROGRESS - previous
          const step = Math.max(MIN_PROGRESS_STEP, Math.round(remaining * 0.15))
          const nextProgress = Math.min(MAX_IN_FLIGHT_PROGRESS, previous + step)
          progressRef.current = nextProgress
          return nextProgress
        })
      }, PROGRESS_TICK_MS)
    }, START_DELAY_MS)
  }, [clearProgressTickTimer, clearStartDelayTimer])

  const finishTransition = useCallback(() => {
    clearStartDelayTimer()
    clearProgressTickTimer()

    if (!loadingRef.current && progressRef.current === 0) {
      return
    }

    progressRef.current = 100
    setProgress(100)
    startDelayTimerRef.current = window.setTimeout(() => {
      loadingRef.current = false
      progressRef.current = 0
      setLoading(false)
      setProgress(0)
    }, COMPLETE_HIDE_DELAY_MS)
  }, [clearProgressTickTimer, clearStartDelayTimer])

  useEffect(() => {
    loadingRef.current = loading
  }, [loading])

  useEffect(() => {
    progressRef.current = progress
  }, [progress])

  useEffect(() => {
    if (previousPathRef.current === pathname) {
      return
    }
    previousPathRef.current = pathname
    finishTransition()
  }, [finishTransition, pathname])

  useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || isModifiedClick(event)) {
        return
      }

      const target = event.target
      if (!(target instanceof Element)) {
        return
      }

      const anchor = target.closest('a[href]')
      if (!(anchor instanceof HTMLAnchorElement)) {
        return
      }

      if (isInternalNavigationAnchor(anchor)) {
        startTransition()
      }
    }

    const handlePopState = () => {
      startTransition()
    }

    document.addEventListener('click', handleDocumentClick, true)
    window.addEventListener('popstate', handlePopState)

    return () => {
      document.removeEventListener('click', handleDocumentClick, true)
      window.removeEventListener('popstate', handlePopState)
      clearStartDelayTimer()
      clearProgressTickTimer()
      loadingRef.current = false
      progressRef.current = 0
      setLoading(false)
      setProgress(0)
    }
  }, [clearProgressTickTimer, clearStartDelayTimer, startTransition])

  if (!loading && progress === 0) {
    return null
  }

  return (
    <>
      <div className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[3px] bg-transparent">
        <div
          aria-hidden="true"
          className="h-full bg-primary shadow-[0_0_10px_hsl(var(--primary)/0.55)] transition-[width,opacity] duration-200 ease-out"
          style={{
            width: `${progress}%`,
            opacity: progress > 0 ? 1 : 0,
          }}
        />
      </div>
      {loading ? (
        <div aria-live="polite" className="fixed inset-0 z-[99]">
          <div className="absolute inset-0 bg-background/45 backdrop-blur-[1px]" />
          <div className="absolute inset-0 flex items-center justify-center px-4">
            <div className="w-full max-w-md rounded-xl border bg-card/95 p-6 text-center shadow-brand-sm">
              <div className="mb-3 inline-flex items-center justify-center rounded-full border p-3">
                <Loader2 className="size-5 animate-spin text-muted-foreground" />
              </div>
              <h2 className="font-heading text-lg font-semibold text-foreground">
                Updating screen
              </h2>
              <p className="mt-2 text-sm text-muted-foreground">
                Loading the next page. This can take a few seconds.
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </>
  )
}

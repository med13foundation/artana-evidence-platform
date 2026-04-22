'use client'

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react'
import { usePathname } from 'next/navigation'
import type { ResearchSpace } from '@/types/research-space'

export interface SpaceContextValue {
  currentSpaceId: string | null
  setCurrentSpaceId: (spaceId: string | null) => void
  isLoading: boolean
  spaces: ResearchSpace[]
  spaceTotal: number
}

const SpaceContext = createContext<SpaceContextValue | undefined>(undefined)

interface SpaceContextProviderProps {
  children: ReactNode
  initialSpaces?: ResearchSpace[]
  initialSpaceId?: string | null
  initialTotal?: number
  isLoading?: boolean
}

export function useSpaceContext() {
  const context = useContext(SpaceContext)
  if (!context) {
    throw new Error('useSpaceContext must be used within SpaceContextProvider')
  }
  return context
}

export function SpaceContextProvider({
  children,
  initialSpaces = [],
  initialSpaceId = null,
  initialTotal,
  isLoading = false,
}: SpaceContextProviderProps) {
  const pathname = usePathname()
  const spaces = useMemo<ResearchSpace[]>(() => initialSpaces, [initialSpaces])
  const spaceTotal = initialTotal ?? spaces.length

  const [currentSpaceId, setCurrentSpaceIdState] = useState<string | null>(() => {
    if (initialSpaceId) {
      return initialSpaceId
    }
    if (typeof window !== 'undefined') {
      return localStorage.getItem('currentSpaceId')
    }
    return null
  })

  useEffect(() => {
    const spaceMatch = pathname.match(/\/spaces\/([^/]+)/)
    if (spaceMatch) {
      const spaceIdFromUrl = spaceMatch[1]
      if (spaceIdFromUrl !== 'new') {
        setCurrentSpaceIdState(spaceIdFromUrl)
        localStorage.setItem('currentSpaceId', spaceIdFromUrl)
        return
      }
    }

    const savedSpaceId = localStorage.getItem('currentSpaceId')
    const savedSpaceExists =
      savedSpaceId !== null && spaces.some((space) => space.id === savedSpaceId)

    if (savedSpaceId && savedSpaceExists) {
      if (savedSpaceId !== currentSpaceId) {
        setCurrentSpaceIdState(savedSpaceId)
      }
      return
    }

    if (savedSpaceId && !savedSpaceExists) {
      localStorage.removeItem('currentSpaceId')
    }

    if (spaces.length > 0) {
      const firstSpaceId = spaces[0].id
      if (firstSpaceId !== currentSpaceId) {
        setCurrentSpaceIdState(firstSpaceId)
        localStorage.setItem('currentSpaceId', firstSpaceId)
      }
    } else if (currentSpaceId !== null) {
      setCurrentSpaceIdState(null)
      localStorage.removeItem('currentSpaceId')
    }
  }, [pathname, spaces, currentSpaceId])

  const setCurrentSpaceId = (spaceId: string | null) => {
    setCurrentSpaceIdState(spaceId)
    if (spaceId) {
      localStorage.setItem('currentSpaceId', spaceId)
    } else {
      localStorage.removeItem('currentSpaceId')
    }
  }

  return (
    <SpaceContext.Provider
      value={{
        currentSpaceId,
        setCurrentSpaceId,
        isLoading,
        spaces,
        spaceTotal,
      }}
    >
      {children}
    </SpaceContext.Provider>
  )
}

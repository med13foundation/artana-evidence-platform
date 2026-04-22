import type { ReactNode } from 'react'
import { render, screen, waitFor } from '@testing-library/react'

import { AiModelSelector } from '@/components/data-sources/AiModelSelector'
import { fetchAvailableModelsClient } from '@/lib/client/ai-models'
import { toast } from 'sonner'

jest.mock('@/lib/client/ai-models', () => ({
  fetchAvailableModelsClient: jest.fn(),
}))

jest.mock('sonner', () => ({
  toast: {
    error: jest.fn(),
  },
}))

jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}))

jest.mock('@/components/ui/select', () => {
  const React = require('react') as typeof import('react')

  return {
    Select: ({
      children,
      disabled,
    }: {
      children: React.ReactNode
      disabled?: boolean
    }) => (
      <div data-testid="mock-select" data-disabled={disabled ? 'true' : 'false'}>
        {children}
      </div>
    ),
    SelectTrigger: React.forwardRef<
      HTMLButtonElement,
      React.ComponentPropsWithoutRef<'button'>
    >(function MockSelectTrigger(props, ref) {
      return <button ref={ref} type="button" {...props} />
    }),
    SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
    SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    SelectItem: ({
      children,
      value,
    }: {
      children: React.ReactNode
      value: string
    }) => <div data-value={value}>{children}</div>,
  }
})

function deferredPromise<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('AiModelSelector', () => {
  const mockFetchAvailableModelsClient = fetchAvailableModelsClient as jest.MockedFunction<
    typeof fetchAvailableModelsClient
  >
  const toastErrorMock = toast.error as jest.MockedFunction<typeof toast.error>
  const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => undefined)

  afterAll(() => {
    consoleErrorSpy.mockRestore()
  })

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('loads and renders query-generation models from the API client', async () => {
    mockFetchAvailableModelsClient.mockResolvedValue({
      models: [
        {
          model_id: 'gpt-5-mini',
          display_name: 'GPT-5 Mini',
          provider: 'openai',
          capabilities: ['query_generation'],
          cost_tier: 'low',
          is_reasoning_model: false,
          is_default: true,
        },
        {
          model_id: 'extractor-pro',
          display_name: 'Extractor Pro',
          provider: 'openai',
          capabilities: ['evidence_extraction'],
          cost_tier: 'high',
          is_reasoning_model: true,
          is_default: false,
        },
      ],
      default_query_model: 'gpt-5-mini',
    })

    render(<AiModelSelector value={null} onChange={jest.fn()} />)

    await waitFor(() => {
      expect(screen.getByText('GPT-5 Mini')).toBeInTheDocument()
    })

    expect(screen.queryByText('Extractor Pro')).not.toBeInTheDocument()
    expect(screen.getByText('(GPT-5 Mini)')).toBeInTheDocument()
    expect(toastErrorMock).not.toHaveBeenCalled()
  })

  it('shows the loading state until the action resolves', async () => {
    const deferred = deferredPromise<Awaited<ReturnType<typeof fetchAvailableModelsClient>>>()
    mockFetchAvailableModelsClient.mockReturnValue(deferred.promise)

    render(<AiModelSelector value={null} onChange={jest.fn()} />)

    expect(screen.getByTestId('mock-select')).toHaveAttribute('data-disabled', 'true')
    expect(screen.getByText('Loading models...')).toBeInTheDocument()

    deferred.resolve({
      models: [],
      default_query_model: 'gpt-5-mini',
    })

    await waitFor(() => {
      expect(screen.getByTestId('mock-select')).toHaveAttribute('data-disabled', 'false')
    })
    expect(screen.getByText('Select a model')).toBeInTheDocument()
  })

  it('shows the existing error toast when the action fails', async () => {
    mockFetchAvailableModelsClient.mockRejectedValue(new Error('Session expired'))

    render(<AiModelSelector value={null} onChange={jest.fn()} />)

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Failed to load available models')
    })
  })
})

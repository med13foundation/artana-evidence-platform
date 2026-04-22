import { fetchAvailableModelsAction, fetchModelsForCapabilityAction } from '@/app/actions/data-sources'

const requireAccessTokenMock = jest.fn()
const getAvailableModelsMock = jest.fn()
const getModelsForCapabilityMock = jest.fn()

jest.mock('@/app/actions/action-utils', () => ({
  requireAccessToken: () => requireAccessTokenMock(),
  getActionErrorMessage: (error: unknown, fallback: string) => {
    const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    if (typeof detail === 'string' && detail.trim().length > 0) {
      return detail
    }
    return error instanceof Error ? error.message : fallback
  },
}))

jest.mock('@/lib/api/ai-models', () => ({
  getAvailableModels: (...args: unknown[]) => getAvailableModelsMock(...args),
  getModelsForCapability: (...args: unknown[]) => getModelsForCapabilityMock(...args),
}))

describe('AI model server actions', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('returns available models on success', async () => {
    requireAccessTokenMock.mockResolvedValue('token-123')
    getAvailableModelsMock.mockResolvedValue({
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
      ],
      default_query_model: 'gpt-5-mini',
    })

    const result = await fetchAvailableModelsAction()

    expect(result).toEqual({
      success: true,
      data: {
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
        ],
        default_query_model: 'gpt-5-mini',
      },
    })
    expect(getAvailableModelsMock).toHaveBeenCalledWith('token-123')
  })

  it('returns a clear error when the session is missing or expired', async () => {
    requireAccessTokenMock.mockRejectedValue(new Error('Session expired'))

    const result = await fetchAvailableModelsAction()

    expect(result).toEqual({
      success: false,
      error: 'Session expired',
    })
  })

  it('formats upstream backend failures for capability queries', async () => {
    requireAccessTokenMock.mockResolvedValue('token-123')
    getModelsForCapabilityMock.mockRejectedValue({
      response: {
        data: {
          detail: 'Upstream failure',
        },
      },
      message: 'Request failed',
    })

    const result = await fetchModelsForCapabilityAction('query_generation')

    expect(result).toEqual({
      success: false,
      error: 'Upstream failure',
    })
    expect(getModelsForCapabilityMock).toHaveBeenCalledWith('query_generation', 'token-123')
  })
})

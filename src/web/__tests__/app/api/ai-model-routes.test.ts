import { GET as getAvailableModelsRoute } from '@/app/api/ai-models/available/route'
import { getAvailableModels } from '@/lib/api/ai-models'

const requireAccessTokenMock = jest.fn()

jest.mock('@/app/actions/action-utils', () => ({
  requireAccessToken: () => requireAccessTokenMock(),
  getActionErrorMessage: (error: unknown, fallback: string) => {
    if (error instanceof Error && error.message.trim().length > 0) {
      return error.message
    }
    return fallback
  },
  getActionErrorStatus: () => undefined,
}))

jest.mock('@/lib/api/ai-models', () => ({
  getAvailableModels: jest.fn(),
}))

describe('AI model API route', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('returns 401 when the session token is missing', async () => {
    requireAccessTokenMock.mockRejectedValue(new Error('Session expired'))

    const response = await getAvailableModelsRoute()

    expect(response.status).toBe(401)
  })

  it('returns available models on success', async () => {
    requireAccessTokenMock.mockResolvedValue('token-123')
    ;(getAvailableModels as jest.Mock).mockResolvedValue({
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

    const response = await getAvailableModelsRoute()

    expect(response.status).toBe(200)
    expect(getAvailableModels).toHaveBeenCalledWith('token-123')
  })
})

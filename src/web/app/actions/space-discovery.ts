"use server"

import { revalidatePath } from "next/cache"
import type { AxiosError } from "axios"
import { apiClient, authHeaders } from "@/lib/api/client"
import { requireAccessToken } from "@/app/actions/action-utils"
import type {
  AddToSpaceRequest,
  CreateSessionRequest,
  DataDiscoverySessionResponse,
  OrchestratedSessionState,
  SourceCatalogEntry,
  UpdateSelectionRequest,
} from "@/types/generated"

type SpaceDiscoveryState = {
  orchestratedState: OrchestratedSessionState
  catalog: SourceCatalogEntry[]
}

type SpaceDiscoveryStateResult =
  | { success: true; data: SpaceDiscoveryState }
  | { success: false; error: string }

type SpaceDiscoverySelectionResult =
  | { success: true; state: OrchestratedSessionState }
  | { success: false; error: string }

type SpaceDiscoveryAddResult =
  | { success: true; addedCount: number }
  | { success: false; error: string }

const DISCOVERY_REQUEST_TIMEOUT_MS = 60000

type IssueObject = {
  msg: string
  loc?: unknown
}

type HttpErrorShape = {
  response?: {
    status?: number
  }
}

function isIssueObject(value: unknown): value is IssueObject {
  return (
    typeof value === "object" &&
    value !== null &&
    "msg" in value &&
    typeof (value as IssueObject).msg === "string"
  )
}

function formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail
  }
  if (isIssueObject(detail)) {
    const location = Array.isArray(detail.loc) ? detail.loc.join(".") : ""
    return location ? `${location}: ${detail.msg}` : detail.msg
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((issue) => formatErrorDetail(issue))
      .filter((value): value is string => Boolean(value))
    return messages.length > 0 ? messages.join("; ") : null
  }
  return null
}

function getErrorStatusCode(error: unknown): number | null {
  if (typeof error !== "object" || error === null) {
    return null
  }

  const httpError = error as HttpErrorShape
  const statusCode = httpError.response?.status
  return typeof statusCode === "number" ? statusCode : null
}

function getErrorMessage(error: unknown, fallback: string): string {
  const axiosError = error as AxiosError<{ detail?: unknown }>
  const statusCode = axiosError.response?.status
  if (statusCode === 401) {
    return "Session expired. Please sign in again."
  }
  if (statusCode === 403) {
    return "You do not have access to this research space."
  }
  if (statusCode === 404) {
    return "Research space not found."
  }
  const timeoutCode = typeof axiosError.code === "string" ? axiosError.code : ""
  const timeoutMessage =
    typeof axiosError.message === "string" ? axiosError.message.toLowerCase() : ""
  if (
    timeoutCode === "ECONNABORTED" ||
    timeoutMessage.includes("timeout")
  ) {
    return "Discovery backend is taking longer than expected. Please retry in a few seconds."
  }
  const detail = axiosError.response?.data?.detail
  const formatted = formatErrorDetail(detail)
  if (formatted) {
    return formatted
  }
  if (axiosError?.message) {
    return axiosError.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return fallback
}

async function ensureSpaceSession(
  spaceId: string,
  token: string
): Promise<DataDiscoverySessionResponse> {
  const requestConfig = {
    ...authHeaders(token),
    timeout: DISCOVERY_REQUEST_TIMEOUT_MS,
  }

  const { data: sessions } = await apiClient.get<DataDiscoverySessionResponse[]>(
    `/research-spaces/${spaceId}/discovery/sessions`,
    requestConfig
  )

  if (sessions.length > 0) {
    return sessions[0]
  }

  const payload: CreateSessionRequest = {
    name: "New Discovery Session",
    initial_parameters: {
      gene_symbol: null,
      search_term: null,
    },
  }

  const { data: created } = await apiClient.post<DataDiscoverySessionResponse>(
    `/research-spaces/${spaceId}/discovery/sessions`,
    payload,
    requestConfig
  )
  return created
}

export async function fetchSpaceDiscoveryState(
  spaceId: string
): Promise<SpaceDiscoveryStateResult> {
  try {
    const token = await requireAccessToken()
    const session = await ensureSpaceSession(spaceId, token)
    const requestConfig = {
      ...authHeaders(token),
      timeout: DISCOVERY_REQUEST_TIMEOUT_MS,
    }
    const [stateResponse, catalogResponse] = await Promise.all([
      apiClient.get<OrchestratedSessionState>(
        `/data-discovery/sessions/${session.id}/state`,
        requestConfig
      ),
      apiClient.get<SourceCatalogEntry[]>(
        `/research-spaces/${spaceId}/discovery/catalog`,
        requestConfig
      ),
    ])

    return {
      success: true,
      data: {
        orchestratedState: stateResponse.data,
        catalog: catalogResponse.data,
      },
    }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== "test") {
      const statusCode = getErrorStatusCode(error)
      if (statusCode === 403 || statusCode === 404) {
        console.warn("[ServerAction] fetchSpaceDiscoveryState unavailable:", {
          spaceId,
          statusCode,
        })
      } else {
        console.error("[ServerAction] fetchSpaceDiscoveryState failed:", error)
      }
    }
    return {
      success: false,
      error: getErrorMessage(error, "Failed to load discovery state"),
    }
  }
}

export async function updateSpaceDiscoverySelection(
  sessionId: string,
  sourceIds: string[],
  path: string
): Promise<SpaceDiscoverySelectionResult> {
  try {
    const token = await requireAccessToken()
    const payload: UpdateSelectionRequest = { source_ids: sourceIds }
    const requestConfig = {
      ...authHeaders(token),
      timeout: DISCOVERY_REQUEST_TIMEOUT_MS,
    }
    const response = await apiClient.post<OrchestratedSessionState>(
      `/data-discovery/sessions/${sessionId}/selection`,
      payload,
      requestConfig
    )
    revalidatePath(path)
    return { success: true, state: response.data }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== "test") {
      console.error("[ServerAction] updateSpaceDiscoverySelection failed:", error)
    }
    return {
      success: false,
      error: getErrorMessage(error, "Failed to update selection"),
    }
  }
}

export async function addSpaceDiscoverySources(
  sessionId: string,
  spaceId: string,
  sourceIds: string[],
  path: string
): Promise<SpaceDiscoveryAddResult> {
  try {
    const token = await requireAccessToken()
    const requestConfig = {
      ...authHeaders(token),
      timeout: DISCOVERY_REQUEST_TIMEOUT_MS,
    }
    const results = await Promise.allSettled(
      sourceIds.map(async (catalogEntryId) => {
        const payload: AddToSpaceRequest = {
          catalog_entry_id: catalogEntryId,
          research_space_id: spaceId,
          source_config: {},
        }
        await apiClient.post<{ data_source_id: string }>(
          `/data-discovery/sessions/${sessionId}/add-to-space`,
          payload,
          requestConfig
        )
        return catalogEntryId
      })
    )

    const failed = results.filter(
      (result): result is PromiseRejectedResult => result.status === "rejected"
    )
    if (failed.length > 0) {
      const firstFailure = failed[0]
      const firstFailureMessage = getErrorMessage(
        firstFailure.reason,
        "Failed to add source to space"
      )

      return {
        success: false,
        error:
          sourceIds.length === 1
            ? firstFailureMessage
            : `Some sources could not be added. ${firstFailureMessage}`,
      }
    }

    revalidatePath(path)
    return { success: true, addedCount: sourceIds.length }
  } catch (error: unknown) {
    if (process.env.NODE_ENV !== "test") {
      console.error("[ServerAction] addSpaceDiscoverySources failed:", error)
    }
    return {
      success: false,
      error: getErrorMessage(error, "Failed to add sources to space"),
    }
  }
}

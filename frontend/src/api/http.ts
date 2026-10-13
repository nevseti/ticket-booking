/**
 * Базовый HTTP-клиент. Все запросы идут на тот же origin (/api), cookie авторизации
 * отправляются автоматически. Ошибки сервера приходят в формате Problem Details
 * (RFC 9457) и превращаются в ApiError с машинным кодом `code`.
 */

export interface ProblemDetails {
  type?: string
  title: string
  status: number
  code: string
  detail?: string
  instance?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly problem: ProblemDetails

  constructor(problem: ProblemDetails) {
    super(problem.detail ?? problem.title)
    this.name = 'ApiError'
    this.status = problem.status
    this.code = problem.code
    this.problem = problem
  }
}

export const API_PREFIX = '/api'

async function toApiError(resp: Response): Promise<ApiError> {
  const contentType = resp.headers.get('content-type') ?? ''
  if (contentType.includes('json')) {
    try {
      const body = (await resp.json()) as Partial<ProblemDetails>
      return new ApiError({
        title: body.title ?? resp.statusText,
        status: body.status ?? resp.status,
        code: body.code ?? 'HTTP_ERROR',
        ...body,
      })
    } catch {
      // тело не JSON — падаем на общий вариант ниже
    }
  }
  return new ApiError({ title: resp.statusText || 'Ошибка сети', status: resp.status, code: 'HTTP_ERROR' })
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('content-type')) {
    headers.set('content-type', 'application/json')
  }
  const resp = await fetch(`${API_PREFIX}${path}`, { credentials: 'include', ...init, headers })
  if (!resp.ok) {
    throw await toApiError(resp)
  }
  if (resp.status === 204) {
    return undefined as T
  }
  return (await resp.json()) as T
}

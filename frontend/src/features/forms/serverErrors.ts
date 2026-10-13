import { ApiError } from '../../api/http'

interface ValidationItem {
  loc: (string | number)[]
  msg: string
}

const FIELD_MESSAGES: Record<string, string> = {
  email: 'Некорректный email',
  password: 'Некорректный пароль',
  name: 'Некорректное имя',
}

/**
 * Ошибки валидации сервера (422, code=VALIDATION_ERROR) → { поле: сообщение }
 * для подсветки конкретных полей формы.
 */
export function serverFieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.code !== 'VALIDATION_ERROR') return {}
  const items = (error.problem.errors as ValidationItem[] | undefined) ?? []
  const result: Record<string, string> = {}
  for (const item of items) {
    const field = item.loc.at(-1)
    if (typeof field === 'string' && !(field in result)) {
      result[field] = FIELD_MESSAGES[field] ?? item.msg
    }
  }
  return result
}

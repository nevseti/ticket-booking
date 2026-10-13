/**
 * Куда вернуть пользователя после входа. Принимаем только внутренние пути,
 * иначе ?next=https://evil.example превратил бы форму входа в открытый редирект.
 */
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/'
  return raw
}

import type { QueryClient } from '@tanstack/react-query'

/**
 * Ключи запросов orval — это URL. После изменения мероприятия сбрасываем всё,
 * что начинается с /api/events или /api/admin/events (списки и карточки).
 */
export function invalidateCatalog(queryClient: QueryClient) {
  return queryClient.invalidateQueries({
    predicate: (query) => {
      const key = String(query.queryKey[0] ?? '')
      return key.startsWith('/api/events') || key.startsWith('/api/admin/events')
    },
  })
}

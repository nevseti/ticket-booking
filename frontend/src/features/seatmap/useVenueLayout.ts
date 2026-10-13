import { useGetVenueLayout } from '../../api/generated/catalog/catalog'

/** Схема площадки статична: загружается один раз за сессию (сервер отдаёт ETag). */
export function useVenueLayout() {
  return useGetVenueLayout({
    query: { staleTime: Infinity, gcTime: Infinity },
  })
}

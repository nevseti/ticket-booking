import { useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

import { getMeQueryKey, useLogout, useMe } from '../../api/generated/identity/identity'
import type { UserOut } from '../../api/generated/model'

/**
 * Текущий пользователь. 401 от /api/me — это не ошибка, а «гость»: user = null.
 */
export function useCurrentUser() {
  const query = useMe({
    query: {
      retry: false,
      staleTime: 5 * 60_000,
    },
  })
  const isGuest = query.error?.status === 401
  return {
    user: query.data ?? null,
    isAdmin: query.data?.role === 'admin',
    isLoading: query.isLoading,
    isGuest,
  }
}

/** Положить пользователя в кэш сразу после входа/регистрации — без лишнего запроса /me. */
export function useSetCurrentUser() {
  const queryClient = useQueryClient()
  return useCallback(
    (user: UserOut) => queryClient.setQueryData(getMeQueryKey(), user),
    [queryClient],
  )
}

export function useSignOut() {
  const queryClient = useQueryClient()
  const logout = useLogout()
  return useCallback(async () => {
    await logout.mutateAsync()
    // Сбрасываем весь кэш: в нём могли остаться приватные данные (заказы, удержания).
    queryClient.clear()
  }, [logout, queryClient])
}

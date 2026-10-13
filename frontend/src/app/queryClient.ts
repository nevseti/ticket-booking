import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '../api/http'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      refetchOnWindowFocus: false,
      // Ошибки 4xx — это ответ сервера, а не сбой сети: повторять их бессмысленно.
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status < 500) && failureCount < 2,
    },
  },
})

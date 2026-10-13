import { useQuery } from '@tanstack/react-query'

import { apiFetch } from './http'

export interface Health {
  status: 'ok'
  version: string
  env: string
}

export function useHealth() {
  return useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => apiFetch<Health>('/health'),
    refetchInterval: 30_000,
    retry: false,
  })
}

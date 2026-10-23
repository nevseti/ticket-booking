import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { getGetSeatmapStatusQueryKey, getStreamSeatmapUrl } from '../../api/generated/booking/booking'
import type { SeatmapStatus } from '../../api/generated/model'

/** Изменение занятости из SSE: места h — удержано, s — продано, f — освободилось;
 * zones — сколько мест стоячей зоны теперь занято. */
export interface SeatmapDelta {
  v: number
  seats: Record<string, 'h' | 's' | 'f'>
  zones: Record<string, number>
}

/**
 * Применить изменение к снимку. Снимок с версией N принимает только изменение N + 1;
 * уже учтённые (≤ N) пропускаются. null — изменение пропущено, снимок нужно перечитать.
 */
export function applyDelta(status: SeatmapStatus, delta: SeatmapDelta): SeatmapStatus | null {
  if (status.version !== 0 && delta.v <= status.version) return status
  if (status.version === 0 || delta.v !== status.version + 1) return null

  const held = new Set(status.held)
  const sold = new Set(status.sold)
  for (const [id, state] of Object.entries(delta.seats)) {
    const seat = Number(id)
    held.delete(seat)
    sold.delete(seat)
    if (state === 'h') held.add(seat)
    else if (state === 's') sold.add(seat)
  }
  return {
    version: delta.v,
    held: [...held],
    sold: [...sold],
    zones: status.zones.map((z) => {
      const taken = delta.zones[String(z.section_id)]
      return taken == null ? z : { ...z, available: z.capacity - taken }
    }),
  }
}

/**
 * Занятость зала в реальном времени: SSE-поток изменений поверх снимка из кэша TanStack Query.
 * Возвращает true, пока поток подключён (тогда частый опрос не нужен).
 */
export function useSeatmapLive(eventId: string, enabled: boolean): boolean {
  const queryClient = useQueryClient()
  const [live, setLive] = useState(false)

  useEffect(() => {
    if (!enabled || typeof EventSource === 'undefined') return
    const key = getGetSeatmapStatusQueryKey(eventId)
    const resync = () => queryClient.invalidateQueries({ queryKey: key })
    const source = new EventSource(getStreamSeatmapUrl(eventId))
    let reconnecting = false

    source.onopen = () => {
      setLive(true)
      // После обрыва изменения могли пройти мимо — перечитываем снимок.
      if (reconnecting) resync()
    }
    source.onerror = () => {
      // Браузер переподключится сам (интервал задаёт сервер в поле retry).
      reconnecting = true
      setLive(false)
    }
    source.addEventListener('resync', resync)
    source.addEventListener('delta', (event) => {
      const delta = JSON.parse((event as MessageEvent<string>).data) as SeatmapDelta
      const current = queryClient.getQueryData<SeatmapStatus>(key)
      if (!current) return
      const next = applyDelta(current, delta)
      if (next) queryClient.setQueryData(key, next)
      else resync()
    })

    return () => {
      source.close()
      setLive(false)
    }
  }, [eventId, enabled, queryClient])

  return live
}

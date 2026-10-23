import { notifications } from '@mantine/notifications'
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'

import {
  getGetSeatmapStatusQueryKey,
  getMyHoldsQueryKey,
  useGetSeatmapStatus,
  useHoldSeat,
  useHoldZone,
  useMyHolds,
  useReleaseHold,
  useReleaseMyHolds,
} from '../../api/generated/booking/booking'
import type { HoldOut } from '../../api/generated/model'
import { ApiError } from '../../api/http'
import { useSeatmapLive } from './useSeatmapLive'

/** Изменения занятости приходят по SSE; опрос — подстраховка. Без потока (обрыв,
 * старый прокси) схема перечитывается чаще. */
const STATUS_POLL_LIVE_MS = 30_000
const STATUS_POLL_FALLBACK_MS = 5_000

const MESSAGES: Record<string, (e: ApiError) => string> = {
  SEAT_UNAVAILABLE: () => 'Это место только что заняли — выберите другое',
  HOLD_LIMIT: (e) => `Можно выбрать не больше ${e.problem.limit ?? 6} мест на мероприятие`,
  NOT_ENOUGH_PLACES: (e) => `В зоне осталось только ${e.problem.available ?? 0} мест`,
  SALES_CLOSED: () => 'Продажи на это мероприятие сейчас закрыты',
  SEAT_NOT_FOR_SALE: () => 'Это место не продаётся на данное мероприятие',
  UNAUTHORIZED: () => 'Войдите, чтобы выбирать места',
}

export function bookingErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code]?.(error) ?? error.message
  }
  return 'Не удалось выполнить действие. Проверьте соединение'
}

function notifyError(error: unknown) {
  notifications.show({ color: 'red', message: bookingErrorMessage(error) })
}

export interface SeatStatus {
  held: Set<number>
  sold: Set<number>
  /** Мои удержанные места: id места → id удержания */
  mine: Map<number, string>
  /** Остаток в стоячих зонах: id сектора → свободно */
  zones: Map<number, number>
}

export function useBooking(eventId: string, { enabled, loggedIn }: { enabled: boolean; loggedIn: boolean }) {
  const queryClient = useQueryClient()
  const live = useSeatmapLive(eventId, enabled)
  const statusQuery = useGetSeatmapStatus(eventId, {
    query: {
      enabled,
      refetchInterval: live ? STATUS_POLL_LIVE_MS : STATUS_POLL_FALLBACK_MS,
      staleTime: 0,
    },
  })
  const myQuery = useMyHolds(eventId, {
    query: { enabled: enabled && loggedIn, refetchInterval: 15_000 },
  })

  const refresh = useCallback(
    () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: getGetSeatmapStatusQueryKey(eventId) }),
        queryClient.invalidateQueries({ queryKey: getMyHoldsQueryKey(eventId) }),
      ]),
    [queryClient, eventId],
  )

  const holdSeat = useHoldSeat({ mutation: { onError: notifyError, onSettled: refresh } })
  const holdZone = useHoldZone({ mutation: { onError: notifyError, onSettled: refresh } })
  const releaseHold = useReleaseHold({ mutation: { onError: notifyError, onSettled: refresh } })
  const releaseAll = useReleaseMyHolds({ mutation: { onError: notifyError, onSettled: refresh } })

  const myHolds: HoldOut[] | undefined = myQuery.data?.items

  const status = useMemo<SeatStatus>(() => {
    const mine = new Map((myHolds ?? []).map((h) => [h.seat_id, h.id]))
    // Место, на которое кликнули только что, сразу показываем выбранным (оптимистично).
    const pendingSeat = holdSeat.isPending ? holdSeat.variables?.data.seat_id : undefined
    if (pendingSeat != null && !mine.has(pendingSeat)) mine.set(pendingSeat, 'pending')
    return {
      held: new Set(statusQuery.data?.held ?? []),
      sold: new Set(statusQuery.data?.sold ?? []),
      mine,
      zones: new Map((statusQuery.data?.zones ?? []).map((z) => [z.section_id, z.available])),
    }
  }, [statusQuery.data, myHolds, holdSeat.isPending, holdSeat.variables])

  return {
    status,
    statusReady: statusQuery.isSuccess,
    live,
    my: myQuery.data,
    holdSeat: (seatId: number) => holdSeat.mutate({ eventId, data: { seat_id: seatId } }),
    holdZone: (sectionId: number, quantity: number) =>
      holdZone.mutateAsync({ eventId, data: { section_id: sectionId, quantity } }),
    release: (holdId: string) => releaseHold.mutate({ holdId }),
    releaseAll: () => releaseAll.mutate({ eventId }),
    busy: holdSeat.isPending || holdZone.isPending || releaseHold.isPending || releaseAll.isPending,
    refresh,
  }
}

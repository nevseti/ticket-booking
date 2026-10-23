import type { EventKind, SaleStatus } from '../api/generated/model'

const rub = new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'RUB',
  maximumFractionDigits: 0,
})

/** Цены на сервере — целые копейки. */
export function formatPrice(kopecks: number): string {
  return rub.format(kopecks / 100)
}

const dateTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'long',
  weekday: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

const shortDateTime = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso))
}

export function formatShortDateTime(iso: string): string {
  return shortDateTime.format(new Date(iso))
}

export const KIND_LABELS: Record<EventKind, string> = {
  concert: 'Концерт',
  show: 'Шоу',
  sport: 'Хоккей',
}

export const KIND_GRADIENTS: Record<EventKind, { from: string; to: string }> = {
  concert: { from: '#7048e8', to: '#e64980' },
  show: { from: '#9c36b5', to: '#f76707' },
  sport: { from: '#1971c2', to: '#0ca678' },
}

export const SALE_STATUS: Record<SaleStatus, { label: string; color: string }> = {
  on_sale: { label: 'В продаже', color: 'teal' },
  not_started: { label: 'Скоро в продаже', color: 'blue' },
  ended: { label: 'Продажи завершены', color: 'gray' },
  cancelled: { label: 'Отменено', color: 'red' },
  draft: { label: 'Черновик', color: 'yellow' },
}

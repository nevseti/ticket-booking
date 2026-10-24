// Общее для сценариев: адрес API, данные теста (мероприятие и токены), схема зала.
import http from 'k6/http'
import { SharedArray } from 'k6/data'

// k6 запускается в docker-сети сервера и ходит в api напрямую: через nginx все
// виртуальные пользователи пришли бы с одного IP и упёрлись в его лимиты (ADR 0008).
export const BASE = __ENV.BASE_URL || 'http://api:8000'

const DATA_FILE = __ENV.DATA_FILE || '/data/loadtest-data.json'
// SharedArray: тысячи токенов хранятся один раз, а не в памяти каждого VU.
export const tokens = new SharedArray('tokens', () => JSON.parse(open(DATA_FILE)).tokens)
export const EVENT_ID = JSON.parse(open(DATA_FILE)).event_id

export function authHeaders(token) {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

/** Схема зала в компактном виде: сидячие места концерта по категориям и стоячие зоны. */
export function loadLayout() {
  const layout = http.get(`${BASE}/api/venue/layout`).json()
  const sections = new Map(layout.sections.map((s) => [s.id, s]))
  const hot = [] // VIP и нижний ярус — за ними охотятся все
  const rest = []
  for (const seat of layout.seats) {
    if (!sections.get(seat.section_id).configs.includes('stage')) continue
    if (seat.category_id === 1 || seat.category_id === 4) hot.push(seat.id)
    else rest.push(seat.id)
  }
  const zones = layout.sections
    .filter((s) => s.kind === 'standing' && s.configs.includes('stage'))
    .map((s) => s.id)
  return { hot, rest, zones }
}

export function pick(list) {
  return list[Math.floor(Math.random() * list.length)]
}

export function uuid4() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
  })
}

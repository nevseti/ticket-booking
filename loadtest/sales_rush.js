// Сценарий «старт продаж»: сотни покупателей одновременно открывают схему, охотятся за
// лучшими местами (VIP и нижний ярус — много конфликтов 409), часть берёт билеты в
// стоячие зоны, затем оплачивает (10 % — с отказом банка: проверка компенсации саги).
// Параллельно зрители просто смотрят схему.
//
// После прогона verify.sql проверяет: ни одно место не продано дважды, деньги сходятся.
import http from 'k6/http'
import exec from 'k6/execution'
import { check, sleep } from 'k6'
import { Counter, Rate } from 'k6/metrics'

import { BASE, EVENT_ID, authHeaders, loadLayout, pick, tokens, uuid4 } from './lib.js'

const BUYERS = Number(__ENV.BUYERS || 150)
const VIEWERS = Number(__ENV.VIEWERS || 50)

const holdOk = new Counter('holds_ok')
const holdConflict = new Counter('holds_conflict') // место успели занять — ожидаемо
const purchases = new Counter('purchases_completed')
const declined = new Counter('purchases_declined') // отказ банка → компенсация саги
const unexpected = new Rate('purchase_unexpected_failure')
// 503 SERVICE_OVERLOADED: сервер честно сбросил нагрузку (пул соединений с БД исчерпан)
const shed = new Counter('requests_shed_503')

export const options = {
  setupTimeout: '60s',
  scenarios: {
    buyers: {
      executor: 'ramping-vus',
      exec: 'buyer',
      startVUs: 0,
      stages: [
        { duration: '15s', target: BUYERS }, // продажи открылись — все ринулись
        { duration: '60s', target: BUYERS },
        { duration: '10s', target: 0 },
      ],
      gracefulRampDown: '15s',
    },
    viewers: {
      executor: 'constant-vus',
      exec: 'viewer',
      vus: VIEWERS,
      duration: '85s',
    },
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.01'], // 409 «место занято» сюда не входит — это норма
    'http_req_duration{name:status}': ['p(95)<300'],
    'http_req_duration{name:hold}': ['p(95)<500'],
    'http_req_duration{name:checkout}': ['p(95)<2500'], // в т. ч. ~600 мс «банка»
    purchase_unexpected_failure: ['rate<0.01'],
    checks: ['rate>0.99'],
  },
}

// 409 (место заняли) — нормальный исход в гонке за местами, а не ошибка сервера.
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 409))

export function setup() {
  return loadLayout()
}

function takenSeats() {
  const res = http.get(`${BASE}/api/events/${EVENT_ID}/seatmap/status`, {
    tags: { name: 'status' },
  })
  check(res, { 'схема загружена': (r) => r.status === 200 })
  if (res.status !== 200) return new Set()
  const body = res.json()
  return new Set([...body.held, ...body.sold])
}

function holdSeats(layout, headers) {
  const taken = takenSeats()
  const want = 1 + Math.floor(Math.random() * 3)
  const pool = Math.random() < 0.8 ? layout.hot : layout.rest
  let got = 0
  for (let attempt = 0; attempt < 6 && got < want; attempt++) {
    const seat = pick(pool)
    if (taken.has(seat)) continue
    const res = http.post(`${BASE}/api/events/${EVENT_ID}/holds`, JSON.stringify({ seat_id: seat }), {
      headers,
      tags: { name: 'hold' },
    })
    if (res.status === 503) shed.add(1)
    check(res, { 'место: 201 или 409': (r) => r.status === 201 || r.status === 409 })
    if (res.status === 201) {
      got++
      holdOk.add(1)
    } else {
      holdConflict.add(1)
    }
    taken.add(seat)
    sleep(0.2 + Math.random() * 0.5) // клики человека
  }
  return got
}

function holdZone(layout, headers) {
  const body = { section_id: pick(layout.zones), quantity: 1 + Math.floor(Math.random() * 2) }
  const res = http.post(`${BASE}/api/events/${EVENT_ID}/holds/zone`, JSON.stringify(body), {
    headers,
    tags: { name: 'hold_zone' },
  })
  check(res, { 'зона: 201 или 409': (r) => r.status === 201 || r.status === 409 })
  return res.status === 201 ? res.json().length : 0
}

export function buyer(layout) {
  // Каждая итерация — новый покупатель со своим аккаунтом: лимиты на пользователя ведут
  // себя как в жизни, где один человек покупает один раз.
  const headers = authHeaders(tokens[exec.scenario.iterationInTest % tokens.length])

  const got = Math.random() < 0.25 ? holdZone(layout, headers) : holdSeats(layout, headers)
  if (got === 0) {
    sleep(1)
    return
  }

  sleep(1 + Math.random() * 2) // проверяет выбор, вводит карту
  const card = Math.random() < 0.1 ? 'tok_decline' : 'tok_ok'
  const res = http.post(
    `${BASE}/api/checkout`,
    JSON.stringify({ event_id: EVENT_ID, payment_token: card }),
    {
      headers: { ...headers, 'Idempotency-Key': uuid4() },
      tags: { name: 'checkout' },
      timeout: '30s',
    },
  )
  if (res.status === 503) shed.add(1)
  const state = res.status === 200 ? res.json().state : null
  const expected = state === 'completed' || (state === 'failed' && card === 'tok_decline')
  check(res, { 'оплата: сага завершилась как ожидалось': () => expected })
  if (state === 'completed') purchases.add(1)
  if (state === 'failed' && card === 'tok_decline') declined.add(1)
  unexpected.add(!expected)
  sleep(1 + Math.random() * 2)
}

export function viewer() {
  // Смотрит схему без SSE (k6 не умеет EventSource) — как браузер в режиме опроса.
  takenSeats()
  sleep(2)
}

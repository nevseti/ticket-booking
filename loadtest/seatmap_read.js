// Эксперимент «модель чтения в Redis против чтения из PostgreSQL».
// Постоянный поток GET /seatmap/status с заданной частотой. Зал заранее заполнен
// (prepare --prefill), чтобы запрос к БД был реалистично тяжёлым. Прогон дважды:
// SEATMAP_READ_MODEL=redis и SEATMAP_READ_MODEL=db (переключатель api в .env).
import http from 'k6/http'
import { check } from 'k6'

import { BASE, EVENT_ID } from './lib.js'

const RATE = Number(__ENV.RATE || 150)

export const options = {
  scenarios: {
    reads: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 50,
      maxVUs: 300,
    },
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
}

export default function () {
  const res = http.get(`${BASE}/api/events/${EVENT_ID}/seatmap/status`, {
    tags: { name: 'status' },
  })
  check(res, { 'status 200': (r) => r.status === 200 })
}

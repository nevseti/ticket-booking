import { useInterval } from '@mantine/hooks'
import { useEffect, useState } from 'react'

function parts(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  return {
    days: Math.floor(total / 86_400),
    hours: Math.floor((total % 86_400) / 3600),
    minutes: Math.floor((total % 3600) / 60),
    seconds: total % 60,
  }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** Обратный отсчёт до момента `to`; по достижении вызывает onDone (например, перезапросить данные). */
export function Countdown({ to, onDone }: { to: string; onDone?: () => void }) {
  const target = new Date(to).getTime()
  const [now, setNow] = useState(() => Date.now())
  const interval = useInterval(() => setNow(Date.now()), 1000, { autoInvoke: true })
  const left = target - now

  useEffect(() => {
    if (left <= 0) {
      interval.stop()
      onDone?.()
    }
  }, [left, interval, onDone])

  const { days, hours, minutes, seconds } = parts(left)
  return (
    <span style={{ fontVariantNumeric: 'tabular-nums' }}>
      {days > 0 && `${days} д `}
      {pad(hours)}:{pad(minutes)}:{pad(seconds)}
    </span>
  )
}

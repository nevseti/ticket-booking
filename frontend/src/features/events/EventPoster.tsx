import { Box } from '@mantine/core'
import { useId } from 'react'

import type { EventKind } from '../../api/generated/model'
import { splitTitle } from '../../shared/eventTitle'
import { HockeyCover } from './covers/HockeyCover'
import { ShowCover } from './covers/ShowCover'
import classes from './EventPoster.module.css'

/**
 * Обложка мероприятия:
 *   есть фото (poster_url) — фото; демо-концерты — снимки артистов со свободной лицензией;
 *   концерт без фото — сгенерированный постер с именем артиста;
 *   хоккей  — эмблемы команд и «VS» (HockeyCover);
 *   шоу     — иллюстрация по теме шоу (ShowCover).
 */

const PALETTE: [string, string][] = [
  ['#5f3dc4', '#e64980'],
  ['#d9480f', '#c2255c'],
  ['#1864ab', '#7048e8'],
  ['#087f5b', '#1971c2'],
  ['#e8590c', '#f08c00'],
  ['#862e9c', '#3b5bdb'],
  ['#a61e4d', '#5f3dc4'],
  ['#0b7285', '#5c940d'],
  ['#364fc7', '#0c8599'],
  ['#c92a2a', '#862e9c'],
]

function hash(value: string): number {
  let h = 0
  for (let i = 0; i < value.length; i++) h = (h * 31 + value.charCodeAt(i)) >>> 0
  return h
}

function headlineSize(text: string, variant: 'card' | 'banner'): number {
  // Размер по общей длине, но так, чтобы самое длинное слово влезло в ширину карточки
  // (у Unbounded в верхнем регистре широкие буквы вроде Щ и Ц — около 1 em).
  const n = text.length
  const byLength = n <= 9 ? 34 : n <= 14 ? 28 : n <= 20 ? 22 : n <= 28 ? 18 : 15
  const longestWord = Math.max(...text.split(/\s+/).map((w) => w.length))
  const byWord = Math.floor(236 / (longestWord * 1.05))
  const size = Math.max(13, Math.min(byLength, byWord))
  return variant === 'banner' ? Math.round(size * 1.35) : size
}

function ConcertLights({ id, seed }: { id: string; seed: number }) {
  const beams = [0, 1, 2, 3, 4].map((i) => {
    const x = 60 + i * 70 + ((seed >>> i) % 30)
    const spread = 70 + ((seed >>> (i + 3)) % 60)
    return `M ${x} -10 L ${x - spread} 260 L ${x + spread / 3} 260 Z`
  })
  const bokeh = Array.from({ length: 9 }, (_, i) => ({
    cx: (seed * (i + 3) * 37) % 400,
    cy: 120 + ((seed >>> i) % 110),
    r: 6 + ((seed >>> (i + 2)) % 18),
  }))
  return (
    <>
      <defs>
        <linearGradient id={`${id}-beam`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
      </defs>
      {beams.map((d) => (
        <path key={d} d={d} fill={`url(#${id}-beam)`} opacity="0.35" />
      ))}
      {bokeh.map((b) => (
        <circle key={`${b.cx}-${b.cy}`} {...b} fill="#fff" opacity="0.12" />
      ))}
    </>
  )
}

function background(seed: number): string {
  const [from, to] = PALETTE[seed % PALETTE.length]
  return `linear-gradient(140deg, ${from}, ${to})`
}

export function EventPoster({
  kind,
  title,
  height,
  posterUrl,
  seed: seedKey,
  variant = 'card',
}: {
  kind: EventKind
  title: string
  height: number
  posterUrl?: string | null
  seed?: string
  /** card — у сгенерированного постера пишем имя артиста; banner — только фон */
  variant?: 'card' | 'banner'
}) {
  const id = useId().replace(/:/g, '')
  const seed = hash(seedKey ?? title)
  const { headline, subtitle } = splitTitle(title)

  if (posterUrl) {
    return (
      <Box h={height} className={classes.poster} style={{ background: '#1a1b1e' }}>
        <img src={posterUrl} alt="" loading="lazy" className={classes.photo} />
      </Box>
    )
  }

  if (kind === 'sport' || kind === 'show') {
    return (
      <Box h={height} className={classes.poster}>
        {kind === 'sport' ? (
          <HockeyCover title={title} id={id} fit={variant} />
        ) : (
          <ShowCover title={title} id={id} fit={variant} />
        )}
      </Box>
    )
  }

  return (
    <Box h={height} className={classes.poster} style={{ background: background(seed) }}>
      <svg className={classes.art} viewBox="0 0 400 240" preserveAspectRatio="xMidYMid slice">
        <defs>
          <filter id={`${id}-grain`}>
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed={seed % 97} />
            <feColorMatrix values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0" />
          </filter>
          <radialGradient id={`${id}-vignette`} cx="50%" cy="40%" r="75%">
            <stop offset="0.55" stopColor="#000" stopOpacity="0" />
            <stop offset="1" stopColor="#000" stopOpacity="0.55" />
          </radialGradient>
        </defs>
        <ConcertLights id={id} seed={seed} />
        <rect width="400" height="240" fill={`url(#${id}-vignette)`} />
        <rect width="400" height="240" filter={`url(#${id}-grain)`} opacity="0.18" />
      </svg>

      {variant === 'card' && (
        <div className={classes.text}>
          {subtitle && <div className={classes.subtitle}>{subtitle}</div>}
          <div className={classes.headline} style={{ fontSize: headlineSize(headline, variant) }}>
            {headline}
          </div>
        </div>
      )}
    </Box>
  )
}

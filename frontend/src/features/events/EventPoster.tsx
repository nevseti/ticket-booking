import { Box } from '@mantine/core'
import { useId } from 'react'

import type { EventKind } from '../../api/generated/model'
import { splitTitle } from '../../shared/eventTitle'
import classes from './EventPoster.module.css'

/**
 * Генерируемая афиша в стиле гастрольного постера: имя артиста крупным шрифтом, свет сцены
 * (концерты), софиты (шоу) или разметка льда и цвета команд (хоккей). Фото артистов не
 * используются — у них есть правообладатели, а сайт публичный.
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

// Цвета хоккейных клубов (для диагональной «формы» на афише матча)
const TEAM_COLORS: Record<string, string> = {
  Динамо: '#0b4ea2',
  СКА: '#d6262f',
  ЦСКА: '#b0101e',
  Спартак: '#e03131',
  'Ак Барс': '#0a7f3f',
  Металлург: '#1c3f94',
}

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
    const x = 60 + i * 70 + ((seed >> i) % 30)
    const spread = 70 + ((seed >> (i + 3)) % 60)
    return `M ${x} -10 L ${x - spread} 260 L ${x + spread / 3} 260 Z`
  })
  const bokeh = Array.from({ length: 9 }, (_, i) => ({
    cx: (seed * (i + 3) * 37) % 400,
    cy: 120 + ((seed >> i) % 110),
    r: 6 + ((seed >> (i + 2)) % 18),
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

function ShowSparkles({ seed }: { seed: number }) {
  const stars = Array.from({ length: 14 }, (_, i) => ({
    x: (seed * (i + 7) * 53) % 400,
    y: (seed * (i + 3) * 29) % 230,
    s: 2 + ((seed >> i) % 5),
  }))
  return (
    <>
      <circle cx="80" cy="-20" r="170" fill="#fff" opacity="0.10" />
      <circle cx="340" cy="-40" r="150" fill="#fff" opacity="0.08" />
      {stars.map((st) => (
        <path
          key={`${st.x}-${st.y}`}
          d={`M ${st.x} ${st.y - st.s * 2} L ${st.x + st.s / 2} ${st.y - st.s / 2} L ${st.x + st.s * 2} ${st.y} L ${st.x + st.s / 2} ${st.y + st.s / 2} L ${st.x} ${st.y + st.s * 2} L ${st.x - st.s / 2} ${st.y + st.s / 2} L ${st.x - st.s * 2} ${st.y} L ${st.x - st.s / 2} ${st.y - st.s / 2} Z`}
          fill="#fff"
          opacity="0.55"
        />
      ))}
    </>
  )
}

function HockeyIce() {
  return (
    <g stroke="#fff" fill="none" opacity="0.28">
      <line x1="200" y1="0" x2="200" y2="240" strokeWidth="5" />
      <line x1="130" y1="0" x2="130" y2="240" strokeWidth="3" />
      <line x1="270" y1="0" x2="270" y2="240" strokeWidth="3" />
      <circle cx="200" cy="120" r="46" strokeWidth="3" />
      <circle cx="60" cy="70" r="30" strokeWidth="2" />
      <circle cx="60" cy="170" r="30" strokeWidth="2" />
      <circle cx="340" cy="70" r="30" strokeWidth="2" />
      <circle cx="340" cy="170" r="30" strokeWidth="2" />
    </g>
  )
}

function background(kind: EventKind, title: string, seed: number): string {
  if (kind === 'sport') {
    const teams = splitTitle(title).headline.split(' — ')
    const left = TEAM_COLORS[teams[0]?.trim()] ?? '#1864ab'
    const right = TEAM_COLORS[teams[1]?.trim()] ?? '#c92a2a'
    if (teams.length < 2) return 'linear-gradient(135deg, #1c2a44, #c69214)'
    return `linear-gradient(115deg, ${left} 0%, ${left} 49.6%, ${right} 50.4%, ${right} 100%)`
  }
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
  /** card — с именем артиста на афише; banner — только фон (заголовок выводится отдельно) */
  variant?: 'card' | 'banner'
}) {
  const id = useId().replace(/:/g, '')
  const seed = hash(seedKey ?? title)
  const { headline, subtitle } = splitTitle(title)

  const text = variant === 'card' && (
    <div className={classes.text}>
      {subtitle && <div className={classes.subtitle}>{subtitle}</div>}
      <div className={classes.headline} style={{ fontSize: headlineSize(headline, variant) }}>
        {headline}
      </div>
    </div>
  )

  if (posterUrl) {
    // Фото со сцены + затемнение снизу, чтобы имя артиста читалось на любом снимке.
    return (
      <Box h={height} className={classes.poster} style={{ background: '#1a1b1e' }}>
        <img src={posterUrl} alt="" loading="lazy" className={classes.photo} />
        {text}
      </Box>
    )
  }

  return (
    <Box h={height} className={classes.poster} style={{ background: background(kind, title, seed) }}>
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
        {kind === 'concert' && <ConcertLights id={id} seed={seed} />}
        {kind === 'show' && <ShowSparkles seed={seed} />}
        {kind === 'sport' && <HockeyIce />}
        <rect width="400" height="240" fill={`url(#${id}-vignette)`} />
        <rect width="400" height="240" filter={`url(#${id}-grain)`} opacity="0.18" />
      </svg>

      {text}
    </Box>
  )
}

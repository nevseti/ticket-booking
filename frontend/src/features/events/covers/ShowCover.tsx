/**
 * Иллюстрированные обложки шоу: тема выбирается по названию.
 *   лёд / Щелкунчик  — каток, снежинки, свет софитов
 *   импровизация     — облачка реплик
 *   стендап          — кирпичная стена, луч прожектора, микрофон на стойке
 *   битбокс          — неоновые звуковые волны и эквалайзер
 */

import { BLEED, COVER_ASPECT, COVER_VIEWBOX, type CoverFit } from './fit'

type Theme = 'ice' | 'improv' | 'standup' | 'beatbox' | 'default'

function showTheme(title: string): Theme {
  const t = title.toLowerCase()
  if (/лед|лёд|щелкун|фигурн/.test(t)) return 'ice'
  if (/импров/.test(t)) return 'improv'
  if (/стендап|stand/.test(t)) return 'standup'
  if (/битбокс|beatbox/.test(t)) return 'beatbox'
  return 'default'
}

function Snowflake({ x, y, s, o }: { x: number; y: number; s: number; o: number }) {
  return (
    <g transform={`translate(${x} ${y})`} stroke="#fff" strokeWidth={s / 6} opacity={o} strokeLinecap="round">
      {[0, 60, 120].map((a) => (
        <line key={a} x1={-s} y1="0" x2={s} y2="0" transform={`rotate(${a})`} />
      ))}
    </g>
  )
}

function Ice({ id }: { id: string }) {
  const flakes = Array.from({ length: 44 }, (_, i) => ({
    x: ((i * 83) % 800) - 200,
    y: (i * 47) % 150,
    s: 3 + (i % 4) * 2,
    o: 0.35 + (i % 3) * 0.2,
  }))
  return (
    <>
      <defs>
        <linearGradient id={`${id}-sky`} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="240">
          <stop offset="0" stopColor="#0b2545" />
          <stop offset="1" stopColor="#3a6ea5" />
        </linearGradient>
        <radialGradient id={`${id}-spot`} cx="50%" cy="85%" r="45%">
          <stop offset="0" stopColor="#fff" stopOpacity="0.8" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect {...BLEED} fill={`url(#${id}-sky)`} />
      <path d="M140 -10 L110 240 L290 240 L260 -10 Z" fill="#fff" opacity="0.08" />
      <ellipse cx="200" cy="215" rx="700" ry="45" fill="#e7f5ff" opacity="0.85" />
      <ellipse cx="200" cy="205" rx="90" ry="22" fill={`url(#${id}-spot)`} />
      {flakes.map((f) => (
        <Snowflake key={`${f.x}-${f.y}`} {...f} />
      ))}
      {/* фигуристка: силуэт в ласточке */}
      <g fill="#0b2545" transform="translate(200 150)">
        <circle cx="-18" cy="-52" r="9" />
        <path d="M-22 -43 L-6 -40 L30 -48 L32 -44 L0 -30 L-4 -10 L-2 18 L4 40 L-4 40 L-12 16 L-16 -12 L-24 -30 Z" />
        <path d="M-12 -30 L-50 -44 L-52 -40 L-16 -24 Z" />
        <path d="M-8 40 L10 40" stroke="#0b2545" strokeWidth="3" />
      </g>
    </>
  )
}

function Improv({ id }: { id: string }) {
  const bubbles = [
    { x: 40, y: 40, w: 120, h: 62, t: 'А если…', c: '#fff' },
    { x: 230, y: 30, w: 130, h: 60, t: '?!', c: '#ffe066' },
    { x: 120, y: 130, w: 160, h: 64, t: 'Сцена — ваша!', c: '#fff' },
  ]
  return (
    <>
      <defs>
        <linearGradient id={`${id}-bg`} gradientUnits="userSpaceOnUse" x1="40" y1="0" x2="360" y2="240">
          <stop offset="0" stopColor="#f76707" />
          <stop offset="1" stopColor="#d6336c" />
        </linearGradient>
      </defs>
      <rect {...BLEED} fill={`url(#${id}-bg)`} />
      {Array.from({ length: 60 }, (_, i) => (
        <circle key={i} cx={((i * 59) % 800) - 200} cy={(i * 37) % 240} r={2 + (i % 3)} fill="#fff" opacity="0.15" />
      ))}
      {bubbles.map((b, i) => (
        <g key={b.t} transform={`rotate(${i === 1 ? 6 : -4} ${b.x + b.w / 2} ${b.y + b.h / 2})`}>
          <rect x={b.x} y={b.y} width={b.w} height={b.h} rx="22" fill={b.c} />
          <path d={`M${b.x + 30} ${b.y + b.h} l-6 18 l22 -18 z`} fill={b.c} />
          <text
            x={b.x + b.w / 2}
            y={b.y + b.h / 2}
            textAnchor="middle"
            dominantBaseline="middle"
            fontFamily="Unbounded, sans-serif"
            fontWeight="800"
            fontSize={b.t.length > 8 ? 15 : 22}
            fill="#c2255c"
          >
            {b.t}
          </text>
        </g>
      ))}
    </>
  )
}

function Standup({ id }: { id: string }) {
  const bricks = []
  for (let row = 0; row < 12; row++) {
    for (let col = -8; col < 16; col++) {
      bricks.push({ x: col * 50 + (row % 2 ? 25 : 0), y: row * 20, k: `${row}-${col}` })
    }
  }
  return (
    <>
      <defs>
        <radialGradient id={`${id}-spot`} gradientUnits="userSpaceOnUse" cx="200" cy="140" r="170">
          <stop offset="0" stopColor="#ffd8a8" stopOpacity="0.85" />
          <stop offset="0.6" stopColor="#ffd8a8" stopOpacity="0.15" />
          <stop offset="1" stopColor="#000" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-cone`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.35" />
          <stop offset="1" stopColor="#fff" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <rect {...BLEED} fill="#3b1d14" />
      {bricks.map((b) => (
        <rect key={b.k} x={b.x + 1} y={b.y + 1} width="48" height="18" rx="2" fill="#6e2f1f" opacity="0.85" />
      ))}
      <rect {...BLEED} fill="#000" opacity="0.45" />
      <rect {...BLEED} fill={`url(#${id}-spot)`} />
      <path d="M170 -10 L230 -10 L290 240 L110 240 Z" fill={`url(#${id}-cone)`} />
      {/* микрофон на стойке */}
      <g stroke="#111" strokeLinecap="round">
        <line x1="200" y1="112" x2="200" y2="214" strokeWidth="5" />
        <line x1="178" y1="216" x2="222" y2="216" strokeWidth="6" />
      </g>
      <rect x="191" y="76" width="18" height="34" rx="9" fill="#212529" />
      <rect x="191" y="76" width="18" height="16" rx="8" fill="#868e96" />
    </>
  )
}

function Beatbox({ id }: { id: string }) {
  const bars = Array.from({ length: 84 }, (_, i) => 18 + Math.abs(Math.sin(i * 0.7) * 70) + (i % 4) * 6)
  const wave = Array.from({ length: 121 }, (_, i) => {
    const x = i * 10 - 400
    const y = 120 + Math.sin(i * 0.55) * 30 * Math.sin(i * 0.13)
    return `${i === 0 ? 'M' : 'L'}${x} ${y.toFixed(1)}`
  }).join(' ')
  return (
    <>
      <defs>
        <linearGradient id={`${id}-bg`} gradientUnits="userSpaceOnUse" x1="40" y1="0" x2="360" y2="240">
          <stop offset="0" stopColor="#12002f" />
          <stop offset="1" stopColor="#2b0a3d" />
        </linearGradient>
        <linearGradient id={`${id}-bar`} x1="0" y1="1" x2="0" y2="0">
          <stop offset="0" stopColor="#15aabf" />
          <stop offset="1" stopColor="#e64980" />
        </linearGradient>
        <filter id={`${id}-glow`}>
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <rect {...BLEED} fill={`url(#${id}-bg)`} />
      {bars.map((h, i) => (
        <rect key={i} x={-386 + i * 14} y={236 - h} width="9" height={h} rx="3" fill={`url(#${id}-bar)`} opacity="0.75" />
      ))}
      <path d={wave} fill="none" stroke="#66d9e8" strokeWidth="3" filter={`url(#${id}-glow)`} />
      <path d={wave} fill="none" stroke="#f783ac" strokeWidth="2" transform="translate(0 14)" opacity="0.7" filter={`url(#${id}-glow)`} />
    </>
  )
}

function Sparkles({ id }: { id: string }) {
  return (
    <>
      <defs>
        <linearGradient id={`${id}-bg`} gradientUnits="userSpaceOnUse" x1="40" y1="0" x2="360" y2="240">
          <stop offset="0" stopColor="#862e9c" />
          <stop offset="1" stopColor="#f76707" />
        </linearGradient>
      </defs>
      <rect {...BLEED} fill={`url(#${id}-bg)`} />
      {Array.from({ length: 36 }, (_, i) => (
        <circle key={i} cx={((i * 71) % 800) - 200} cy={(i * 43) % 240} r={2 + (i % 4)} fill="#fff" opacity="0.4" />
      ))}
    </>
  )
}

export function ShowCover({ title, id, fit }: { title: string; id: string; fit: CoverFit }) {
  const theme = showTheme(title)
  return (
    <svg viewBox={COVER_VIEWBOX} preserveAspectRatio={COVER_ASPECT[fit]} width="100%" height="100%">
      {theme === 'ice' && <Ice id={id} />}
      {theme === 'improv' && <Improv id={id} />}
      {theme === 'standup' && <Standup id={id} />}
      {theme === 'beatbox' && <Beatbox id={id} />}
      {theme === 'default' && <Sparkles id={id} />}
    </svg>
  )
}

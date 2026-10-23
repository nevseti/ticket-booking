import { splitTitle } from '../../../shared/eventTitle'
import { BLEED, COVER_ASPECT, COVER_VIEWBOX, type CoverFit } from './fit'

/**
 * Обложка хоккейного матча: «команда против команды». Эмблемы — собственные щиты в цветах
 * клубов с монограммой, а не настоящие логотипы (это товарные знаки клубов).
 */

interface Team {
  name: string
  mono: string
  primary: string
  secondary: string
}

const TEAMS: Record<string, Team> = {
  Динамо: { name: 'Динамо', mono: 'Д', primary: '#0b3d91', secondary: '#ffffff' },
  СКА: { name: 'СКА', mono: 'СКА', primary: '#1f3b8f', secondary: '#e03131' },
  ЦСКА: { name: 'ЦСКА', mono: 'ЦСКА', primary: '#b0101e', secondary: '#1d3f91' },
  Спартак: { name: 'Спартак', mono: 'С', primary: '#c8102e', secondary: '#ffffff' },
  'Ак Барс': { name: 'Ак Барс', mono: 'АБ', primary: '#0a7f3f', secondary: '#ffffff' },
  Запад: { name: 'Запад', mono: 'З', primary: '#1c2a44', secondary: '#f2c94c' },
  Восток: { name: 'Восток', mono: 'В', primary: '#7a0f1f', secondary: '#f2c94c' },
}

function teamsFromTitle(title: string): [Team, Team] {
  const { headline } = splitTitle(title)
  if (/звёзд|звезд/i.test(headline)) return [TEAMS['Запад'], TEAMS['Восток']]
  const [left, right] = headline.split(/\s+—\s+/)
  const fallback = (name: string, color: string): Team => ({
    name,
    mono: name.slice(0, 1).toUpperCase(),
    primary: color,
    secondary: '#ffffff',
  })
  return [
    TEAMS[left?.trim()] ?? fallback(left ?? 'Хозяева', '#1864ab'),
    TEAMS[right?.trim()] ?? fallback(right ?? 'Гости', '#c92a2a'),
  ]
}

const SHIELD = 'M50 4 L94 18 V58 C94 88 72 106 50 116 C28 106 6 88 6 58 V18 Z'

function Badge({ team, x, id }: { team: Team; x: number; id: string }) {
  const monoSize = team.mono.length >= 4 ? 18 : team.mono.length === 3 ? 22 : team.mono.length === 2 ? 30 : 44
  return (
    <g transform={`translate(${x} 26)`}>
      <defs>
        <linearGradient id={`${id}-shine`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.35" />
          <stop offset="0.5" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <clipPath id={`${id}-clip`}>
          <path d={SHIELD} />
        </clipPath>
      </defs>
      <path d={SHIELD} fill={team.primary} stroke={team.secondary} strokeWidth="5" />
      <g clipPath={`url(#${id}-clip)`}>
        <rect x="-10" y="70" width="130" height="14" fill={team.secondary} opacity="0.9" transform="rotate(-18 50 77)" />
        <path d={SHIELD} fill={`url(#${id}-shine)`} />
      </g>
      <text
        x="50"
        y="60"
        textAnchor="middle"
        dominantBaseline="middle"
        fill="#fff"
        fontFamily="Unbounded, sans-serif"
        fontWeight="800"
        fontSize={monoSize}
        style={{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.25)', strokeWidth: 2 }}
      >
        {team.mono}
      </text>
      <text
        x="50"
        y="134"
        textAnchor="middle"
        fill="#fff"
        fontFamily="Unbounded, sans-serif"
        fontWeight="700"
        fontSize="13"
        letterSpacing="1"
      >
        {team.name.toUpperCase()}
      </text>
    </g>
  )
}

export function HockeyCover({ title, id, fit }: { title: string; id: string; fit: CoverFit }) {
  const [home, away] = teamsFromTitle(title)
  return (
    <svg viewBox={COVER_VIEWBOX} preserveAspectRatio={COVER_ASPECT[fit]} width="100%" height="100%">
      <defs>
        <linearGradient id={`${id}-bg`} gradientUnits="userSpaceOnUse" x1="40" y1="0" x2="360" y2="0">
          <stop offset="0" stopColor={home.primary} />
          <stop offset="0.5" stopColor="#0b1220" />
          <stop offset="1" stopColor={away.primary} />
        </linearGradient>
        <radialGradient id={`${id}-ice`} cx="50%" cy="100%" r="60%">
          <stop offset="0" stopColor="#dbeafe" stopOpacity="0.55" />
          <stop offset="1" stopColor="#dbeafe" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect {...BLEED} fill={`url(#${id}-bg)`} />
      {/* огни арены */}
      {Array.from({ length: 64 }, (_, i) => (
        <circle key={i} cx={-388 + i * 25} cy={10 + (i % 3) * 5} r={2.2} fill="#fff" opacity="0.6" />
      ))}
      <ellipse cx="200" cy="250" rx="260" ry="70" fill={`url(#${id}-ice)`} />
      <line x1="200" y1="190" x2="200" y2="240" stroke="#e03131" strokeWidth="3" opacity="0.6" />
      <Badge team={home} x={54} id={`${id}-h`} />
      <Badge team={away} x={246} id={`${id}-a`} />
      <text
        x="200"
        y="92"
        textAnchor="middle"
        dominantBaseline="middle"
        fill="#fff"
        fontFamily="Unbounded, sans-serif"
        fontWeight="800"
        fontSize="30"
        opacity="0.95"
      >
        VS
      </text>
    </svg>
  )
}

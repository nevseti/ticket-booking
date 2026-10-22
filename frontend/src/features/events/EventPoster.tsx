import { Box, Center } from '@mantine/core'

import type { EventKind } from '../../api/generated/model'
import { KIND_GRADIENTS } from '../../shared/format'
import { KindIcon } from './KindIcon'

// Палитра «постеров» без картинок: у каждого мероприятия свой градиент,
// стабильный между перезагрузками (выбирается по хэшу id).
const PALETTE: [string, string][] = [
  ['#7048e8', '#e64980'],
  ['#f76707', '#d6336c'],
  ['#1971c2', '#7048e8'],
  ['#0ca678', '#1971c2'],
  ['#e8590c', '#fab005'],
  ['#ae3ec9', '#4263eb'],
  ['#c2255c', '#5f3dc4'],
  ['#099268', '#66a80f'],
  ['#1864ab', '#0b7285'],
  ['#d9480f', '#862e9c'],
]

function hash(value: string): number {
  let h = 0
  for (let i = 0; i < value.length; i++) h = (h * 31 + value.charCodeAt(i)) >>> 0
  return h
}

/** Постер: картинка, если задана, иначе градиент (по id мероприятия или по типу). */
export function EventPoster({
  kind,
  posterUrl,
  height,
  seed,
}: {
  kind: EventKind
  posterUrl?: string | null
  height: number
  seed?: string
}) {
  const [from, to] = seed
    ? PALETTE[hash(seed) % PALETTE.length]
    : [KIND_GRADIENTS[kind].from, KIND_GRADIENTS[kind].to]
  if (posterUrl) {
    return (
      <Box
        h={height}
        style={{ background: `center / cover no-repeat url("${posterUrl}"), ${from}` }}
      />
    )
  }
  return (
    <Center
      h={height}
      c="white"
      style={{
        background: `radial-gradient(circle at 20% 15%, rgba(255,255,255,0.25), transparent 45%), linear-gradient(135deg, ${from}, ${to})`,
      }}
    >
      <Box opacity={0.85}>
        <KindIcon kind={kind} size={Math.round(height / 3)} />
      </Box>
    </Center>
  )
}

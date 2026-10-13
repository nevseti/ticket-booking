import {
  IconBallBasketball,
  IconMasksTheater,
  IconMicrophone2,
  IconMoodHappy,
  IconSparkles,
} from '@tabler/icons-react'

import type { EventKind } from '../../api/generated/model'

const ICONS = {
  concert: IconMicrophone2,
  theatre: IconMasksTheater,
  sport: IconBallBasketball,
  show: IconMoodHappy,
  other: IconSparkles,
} satisfies Record<EventKind, unknown>

export function KindIcon({ kind, size = 24 }: { kind: EventKind; size?: number }) {
  const Icon = ICONS[kind]
  return <Icon size={size} stroke={1.5} />
}

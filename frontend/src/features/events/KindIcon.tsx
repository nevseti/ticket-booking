import { IconIceSkating, IconMicrophone2, IconSparkles } from '@tabler/icons-react'

import type { EventKind } from '../../api/generated/model'

const ICONS = {
  concert: IconMicrophone2,
  show: IconSparkles,
  sport: IconIceSkating,
} satisfies Record<EventKind, unknown>

export function KindIcon({ kind, size = 24 }: { kind: EventKind; size?: number }) {
  const Icon = ICONS[kind]
  return <Icon size={size} stroke={1.5} />
}

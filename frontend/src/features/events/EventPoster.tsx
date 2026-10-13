import { Box, Center } from '@mantine/core'

import type { EventKind } from '../../api/generated/model'
import { KIND_GRADIENTS } from '../../shared/format'
import { KindIcon } from './KindIcon'

/** Постер: картинка, если задана, иначе градиент по типу мероприятия. */
export function EventPoster({
  kind,
  posterUrl,
  height,
}: {
  kind: EventKind
  posterUrl?: string | null
  height: number
}) {
  const { from, to } = KIND_GRADIENTS[kind]
  if (posterUrl) {
    return (
      <Box
        h={height}
        style={{ background: `center / cover no-repeat url("${posterUrl}"), ${from}` }}
      />
    )
  }
  return (
    <Center h={height} c="white" style={{ background: `linear-gradient(135deg, ${from}, ${to})` }}>
      <Box opacity={0.85}>
        <KindIcon kind={kind} size={Math.round(height / 3)} />
      </Box>
    </Center>
  )
}

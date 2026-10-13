import { Badge, Card, Group, Stack, Text } from '@mantine/core'
import { Link } from 'react-router'

import type { EventCard as EventCardData } from '../../api/generated/model'
import { formatDateTime, formatPrice, formatShortDateTime, KIND_LABELS, SALE_STATUS } from '../../shared/format'
import { EventPoster } from './EventPoster'

export function EventCard({ event }: { event: EventCardData }) {
  const status = SALE_STATUS[event.sale_status]

  return (
    <Card
      component={Link}
      to={`/events/${event.id}`}
      withBorder
      padding={0}
      radius="md"
      style={{ overflow: 'hidden' }}
    >
      <EventPoster kind={event.kind} posterUrl={event.poster_url} height={150} />
      <Stack gap={6} p="md">
        <Group justify="space-between" gap="xs">
          <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
            {KIND_LABELS[event.kind]}
          </Text>
          {event.sale_status !== 'on_sale' && (
            <Badge size="sm" variant="light" color={status.color}>
              {event.sale_status === 'not_started'
                ? `с ${formatShortDateTime(event.sales_start_at)}`
                : status.label}
            </Badge>
          )}
        </Group>
        <Text fw={700} lineClamp={2} mih={44}>
          {event.title}
        </Text>
        <Text size="sm" c="dimmed">
          {formatDateTime(event.starts_at)}
        </Text>
        {event.min_price_kopecks != null && (
          <Text size="sm" fw={600}>
            от {formatPrice(event.min_price_kopecks)}
          </Text>
        )}
      </Stack>
    </Card>
  )
}

import { Badge, Card, Group, Stack, Text } from '@mantine/core'
import { Link } from 'react-router'

import type { EventCard as EventCardData } from '../../api/generated/model'
import { formatDateTime, formatPrice, formatShortDateTime, KIND_LABELS, SALE_STATUS } from '../../shared/format'
import classes from './EventCard.module.css'
import { EventPoster } from './EventPoster'

export function EventCard({ event }: { event: EventCardData }) {
  const status = SALE_STATUS[event.sale_status]

  return (
    <Card
      component={Link}
      to={`/events/${event.id}`}
      withBorder
      padding={0}
      radius="lg"
      className={classes.card}
      aria-label={event.title}
    >
      <EventPoster
        kind={event.kind}
        title={event.title}
        posterUrl={event.poster_url}
        height={210}
        seed={event.id}
      />
      <Stack gap={6} p="md">
        <Group justify="space-between" gap="xs">
          <Text size="xs" c="dimmed" tt="uppercase" fw={700}>
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
        <Text size="sm">{formatDateTime(event.starts_at)}</Text>
        <Group justify="space-between">
          {event.min_price_kopecks != null && (
            <Text fw={700}>от {formatPrice(event.min_price_kopecks)}</Text>
          )}
          {event.sale_status === 'on_sale' && (
            <Text size="sm" fw={600} c="var(--mantine-primary-color-filled)">
              Купить →
            </Text>
          )}
        </Group>
      </Stack>
    </Card>
  )
}

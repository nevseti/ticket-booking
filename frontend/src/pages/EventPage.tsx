import {
  Alert,
  Anchor,
  Badge,
  Center,
  Grid,
  Group,
  Loader,
  Paper,
  Skeleton,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { IconArrowLeft, IconCalendarEvent, IconMapPin } from '@tabler/icons-react'
import { useMemo } from 'react'
import { Link, useParams } from 'react-router'

import { useGetEvent } from '../api/generated/catalog/catalog'
import type { EventDetail } from '../api/generated/model'
import { Countdown } from '../features/events/Countdown'
import { EventPoster } from '../features/events/EventPoster'
import { SeatMap } from '../features/seatmap/SeatMap'
import { useVenueLayout } from '../features/seatmap/useVenueLayout'
import { formatDateTime, formatPrice, KIND_LABELS, SALE_STATUS } from '../shared/format'

function SaleBanner({ event, onSalesOpen }: { event: EventDetail; onSalesOpen: () => void }) {
  switch (event.sale_status) {
    case 'on_sale':
      return (
        <Alert color="teal" variant="light">
          Билеты в продаже. Выбор мест на схеме появится на следующем этапе разработки.
        </Alert>
      )
    case 'not_started':
      return (
        <Alert color="blue" variant="light" title="Продажи ещё не начались">
          Откроются {formatDateTime(event.sales_start_at)} — через{' '}
          <Countdown to={event.sales_start_at} onDone={onSalesOpen} />
        </Alert>
      )
    case 'ended':
      return (
        <Alert color="gray" variant="light">
          Продажи завершены.
        </Alert>
      )
    case 'cancelled':
      return (
        <Alert color="red" variant="light">
          Мероприятие отменено.
        </Alert>
      )
    default:
      return (
        <Alert color="yellow" variant="light">
          Черновик: мероприятие видно только администраторам.
        </Alert>
      )
  }
}

export function EventPage() {
  const { eventId = '' } = useParams()
  const eventQuery = useGetEvent(eventId)
  const layoutQuery = useVenueLayout()
  const event = eventQuery.data

  const prices = useMemo(
    () => new Map(event?.prices.map((p) => [p.category_id, p.price_kopecks])),
    [event?.prices],
  )

  if (eventQuery.isLoading) {
    return (
      <Center py={80}>
        <Loader />
      </Center>
    )
  }
  if (eventQuery.error || !event) {
    return (
      <Stack align="center" py={80} gap="xs">
        <Title order={3}>Мероприятие не найдено</Title>
        <Anchor component={Link} to="/">
          Вернуться к афише
        </Anchor>
      </Stack>
    )
  }

  const status = SALE_STATUS[event.sale_status]

  return (
    <Stack gap="lg" py="lg">
      <Anchor component={Link} to="/" size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} /> Афиша
        </Group>
      </Anchor>

      <Grid gap="lg">
        <Grid.Col span={{ base: 12, sm: 4 }}>
          <Paper radius="md" style={{ overflow: 'hidden' }}>
            <EventPoster kind={event.kind} posterUrl={event.poster_url} height={220} />
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, sm: 8 }}>
          <Stack gap="sm">
            <Group gap="xs">
              <Badge variant="light">{KIND_LABELS[event.kind]}</Badge>
              <Badge variant="light" color={status.color}>
                {status.label}
              </Badge>
            </Group>
            <Title order={1}>{event.title}</Title>
            <Group gap="lg" c="dimmed">
              <Group gap={6}>
                <IconCalendarEvent size={18} />
                <Text>{formatDateTime(event.starts_at)}</Text>
              </Group>
              <Group gap={6}>
                <IconMapPin size={18} />
                <Text>
                  {event.venue.name}, {event.venue.address}
                </Text>
              </Group>
            </Group>
            {event.description && <Text>{event.description}</Text>}
            <Group gap="xs">
              {event.prices.map((p) => (
                <Badge
                  key={p.category_id}
                  variant="dot"
                  color={p.color}
                  size="lg"
                  styles={{ root: { textTransform: 'none' } }}
                >
                  {p.category_name} — {formatPrice(p.price_kopecks)}
                </Badge>
              ))}
            </Group>
          </Stack>
        </Grid.Col>
      </Grid>

      <SaleBanner event={event} onSalesOpen={() => eventQuery.refetch()} />

      {layoutQuery.data ? (
        <SeatMap layout={layoutQuery.data} prices={prices} />
      ) : (
        <Skeleton h={480} radius="md" />
      )}
    </Stack>
  )
}

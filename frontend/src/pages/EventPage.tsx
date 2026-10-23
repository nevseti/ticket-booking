import {
  Alert,
  Anchor,
  Badge,
  Box,
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
import { notifications } from '@mantine/notifications'
import { IconArrowLeft, IconCalendarEvent, IconMapPin } from '@tabler/icons-react'
import { useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { useGetEvent } from '../api/generated/catalog/catalog'
import type { EventDetail, SectionOut } from '../api/generated/model'
import { useCurrentUser } from '../features/auth/useCurrentUser'
import { BookingPanel } from '../features/booking/BookingPanel'
import { bookingErrorMessage, useBooking } from '../features/booking/useBooking'
import { ZoneModal } from '../features/booking/ZoneModal'
import { Countdown } from '../features/events/Countdown'
import { EventPoster } from '../features/events/EventPoster'
import { SeatMap } from '../features/seatmap/SeatMap'
import { useVenueLayout } from '../features/seatmap/useVenueLayout'
import { formatDateTime, formatPrice, KIND_LABELS, SALE_STATUS } from '../shared/format'
import classes from './EventPage.module.css'

function SaleBanner({ event, onSalesOpen }: { event: EventDetail; onSalesOpen: () => void }) {
  switch (event.sale_status) {
    case 'on_sale':
      return null
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

function Hero({ event }: { event: EventDetail }) {
  const status = SALE_STATUS[event.sale_status]
  return (
    <Paper radius="lg" className={classes.hero}>
      <Box className={classes.heroArt}>
        <EventPoster
          kind={event.kind}
          title={event.title}
          posterUrl={event.poster_url}
          height={320}
          seed={event.id}
          variant="banner"
        />
      </Box>
      <Stack gap="sm" className={classes.heroContent}>
        <Group gap="xs">
          <Badge variant="white" color="dark">
            {KIND_LABELS[event.kind]}
          </Badge>
          <Badge variant="filled" color={status.color}>
            {status.label}
          </Badge>
        </Group>
        <Title order={1} className={classes.heroTitle}>
          {event.title}
        </Title>
        <Group gap="lg" className={classes.heroMeta}>
          <Group gap={6}>
            <IconCalendarEvent size={18} />
            <Text>{formatDateTime(event.starts_at)}</Text>
          </Group>
          <Group gap={6}>
            <IconMapPin size={18} />
            <Text>{event.venue.name}</Text>
          </Group>
        </Group>
      </Stack>
    </Paper>
  )
}

export function EventPage() {
  const { eventId = '' } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const eventQuery = useGetEvent(eventId)
  const layoutQuery = useVenueLayout()
  const { user } = useCurrentUser()
  const event = eventQuery.data
  const onSale = event?.sale_status === 'on_sale'
  const booking = useBooking(eventId, { enabled: onSale, loggedIn: Boolean(user) })
  const [zone, setZone] = useState<SectionOut | null>(null)

  const prices = useMemo(
    () => new Map(event?.prices.map((p) => [p.category_id, p.price_kopecks])),
    [event?.prices],
  )
  const categories = useMemo(
    () => new Map(layoutQuery.data?.categories.map((c) => [c.id, c])),
    [layoutQuery.data?.categories],
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

  const requireLogin = () => {
    notifications.show({ message: 'Войдите, чтобы выбирать места' })
    navigate(`/login?next=${encodeURIComponent(location.pathname)}`)
  }

  const held = booking.my?.items.length ?? 0
  const limit = booking.my?.limit ?? 6

  const map = layoutQuery.data ? (
    <SeatMap
      layout={layoutQuery.data}
      hallConfig={event.hall_config}
      prices={prices}
      status={onSale && booking.statusReady ? booking.status : undefined}
      onSeatClick={
        onSale
          ? (seat) => {
              if (!user) return requireLogin()
              const holdId = booking.status.mine.get(seat.id)
              if (holdId && holdId !== 'pending') booking.release(holdId)
              else if (!holdId) booking.holdSeat(seat.id)
            }
          : undefined
      }
      onZoneClick={onSale ? (section) => (user ? setZone(section) : requireLogin()) : undefined}
    />
  ) : (
    <Skeleton h={560} radius="md" />
  )

  return (
    <Stack gap="lg" py="lg">
      <Anchor component={Link} to="/" size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} /> Афиша
        </Group>
      </Anchor>

      <Hero event={event} />

      {event.description && (
        <Text size="lg" maw={820}>
          {event.description}
        </Text>
      )}

      <SaleBanner event={event} onSalesOpen={() => eventQuery.refetch()} />

      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: onSale ? 8 : 12 }}>
          <Stack gap="sm">
            {map}
            <Group gap="md" className={classes.legend}>
              {event.prices.map((p) => (
                <Group key={p.category_id} gap={6}>
                  <span className={classes.dot} style={{ background: p.color }} />
                  <Text size="sm">
                    {p.category_name} <b>{formatPrice(p.price_kopecks)}</b>
                  </Text>
                </Group>
              ))}
              {onSale && (
                <>
                  <Group gap={6}>
                    <span className={`${classes.dot} ${classes.dotTaken}`} />
                    <Text size="sm">Занято</Text>
                  </Group>
                  <Group gap={6}>
                    <span className={`${classes.dot} ${classes.dotMine}`} />
                    <Text size="sm">Ваш выбор</Text>
                  </Group>
                </>
              )}
            </Group>
          </Stack>
        </Grid.Col>
        {onSale && (
          <Grid.Col span={{ base: 12, md: 4 }}>
            {user ? (
              <BookingPanel
                eventId={eventId}
                my={booking.my}
                categories={categories}
                busy={booking.busy}
                onRelease={booking.release}
                onReleaseAll={booking.releaseAll}
                onExpired={booking.refresh}
              />
            ) : (
              <Paper withBorder radius="md" p="lg">
                <Stack gap="sm">
                  <Text fw={700}>Выбор мест</Text>
                  <Text size="sm" c="dimmed">
                    Войдите, чтобы выбирать места на схеме: выбранные места удерживаются за вами
                    10 минут.
                  </Text>
                  <Anchor
                    component={Link}
                    to={`/login?next=${encodeURIComponent(location.pathname)}`}
                    fw={600}
                  >
                    Войти или зарегистрироваться →
                  </Anchor>
                </Stack>
              </Paper>
            )}
          </Grid.Col>
        )}
      </Grid>

      <ZoneModal
        key={zone?.id ?? 'closed'}
        zone={zone}
        price={zone?.category_id != null ? prices.get(zone.category_id) : undefined}
        available={zone ? (booking.status.zones.get(zone.id) ?? zone.capacity) : 0}
        canAdd={limit - held}
        loading={booking.busy}
        onClose={() => setZone(null)}
        onConfirm={async (quantity) => {
          if (!zone) return
          try {
            await booking.holdZone(zone.id, quantity)
            notifications.show({ color: 'teal', message: `${zone.name}: билетов — ${quantity}` })
            setZone(null)
          } catch (error) {
            notifications.show({ color: 'red', message: bookingErrorMessage(error) })
          }
        }}
      />
    </Stack>
  )
}

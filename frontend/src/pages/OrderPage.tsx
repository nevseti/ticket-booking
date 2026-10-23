import { Alert, Anchor, Center, Group, Loader, Stack, Text, Title } from '@mantine/core'
import { IconArrowLeft, IconConfetti } from '@tabler/icons-react'
import { QRCodeSVG } from 'qrcode.react'
import { Link, useParams, useSearchParams } from 'react-router'

import type { TicketOut } from '../api/generated/model'
import { useGetOrder } from '../api/generated/orders/orders'
import { formatDateTime, formatPrice } from '../shared/format'
import classes from './OrderPage.module.css'

function TicketStub({
  ticket,
  title,
  startsAt,
}: {
  ticket: TicketOut
  title: string
  startsAt: string
}) {
  return (
    <div className={classes.ticket}>
      <div className={classes.main}>
        <Text size="xs" tt="uppercase" fw={700} c="dimmed">
          Электронный билет
        </Text>
        <Text className={classes.title}>{title}</Text>
        <Text size="sm">{formatDateTime(startsAt)}</Text>
        <Group gap="xl" mt="sm">
          <div>
            <Text size="xs" c="dimmed">
              Сектор
            </Text>
            <Text fw={700}>{ticket.section_name}</Text>
          </div>
          {ticket.standing ? (
            <div>
              <Text size="xs" c="dimmed">
                Место
              </Text>
              <Text fw={700}>Стоячее</Text>
            </div>
          ) : (
            <>
              <div>
                <Text size="xs" c="dimmed">
                  Ряд
                </Text>
                <Text fw={700}>{ticket.row}</Text>
              </div>
              <div>
                <Text size="xs" c="dimmed">
                  Место
                </Text>
                <Text fw={700}>{ticket.number}</Text>
              </div>
            </>
          )}
        </Group>
        <Text size="sm" c="dimmed" mt="sm">
          {ticket.category_name} · {formatPrice(ticket.price_kopecks)}
        </Text>
      </div>
      <div className={classes.stub}>
        <div className={classes.qr}>
          <QRCodeSVG value={ticket.code} size={116} level="M" />
        </div>
        <Text size="xs" c="dimmed" ta="center">
          Покажите на входе
        </Text>
      </div>
    </div>
  )
}

export function OrderPage() {
  const { orderId = '' } = useParams()
  const [params] = useSearchParams()
  const { data: order, isLoading, error } = useGetOrder(orderId)

  if (isLoading) {
    return (
      <Center py={80}>
        <Loader />
      </Center>
    )
  }
  if (error || !order) {
    return (
      <Stack align="center" py={80}>
        <Title order={3}>Заказ не найден</Title>
        <Anchor component={Link} to="/orders">
          Мои заказы
        </Anchor>
      </Stack>
    )
  }

  return (
    <Stack py="lg" gap="lg">
      <Anchor component={Link} to="/orders" size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} /> Мои заказы
        </Group>
      </Anchor>
      {params.get('new') && (
        <Alert color="teal" variant="light" icon={<IconConfetti />} title="Оплата прошла!">
          Билеты ниже. Их копия придёт на почту (после этапа уведомлений).
        </Alert>
      )}
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={1}>Заказ № {order.id.slice(-8).toUpperCase()}</Title>
          <Text c="dimmed">
            {order.tickets_count} шт. · {formatPrice(order.total_kopecks)}
          </Text>
        </div>
      </Group>
      <Stack gap="md">
        {order.tickets.map((ticket) => (
          <TicketStub
            key={ticket.id}
            ticket={ticket}
            title={order.event_title}
            startsAt={order.event_starts_at}
          />
        ))}
      </Stack>
    </Stack>
  )
}

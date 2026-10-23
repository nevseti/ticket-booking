import { Badge, Button, Card, Center, Group, Loader, SimpleGrid, Stack, Text, Title } from '@mantine/core'
import { Link } from 'react-router'

import { useMyOrders } from '../api/generated/orders/orders'
import { formatDateTime, formatPrice } from '../shared/format'

function tickets(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'билет'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'билета'
  return 'билетов'
}

export function OrdersPage() {
  const { data, isLoading } = useMyOrders()

  if (isLoading) {
    return (
      <Center py={80}>
        <Loader />
      </Center>
    )
  }

  return (
    <Stack py="lg" gap="lg">
      <Title order={1}>Мои заказы</Title>
      {data?.length === 0 ? (
        <Stack align="center" py={60} gap="sm">
          <Text c="dimmed">Заказов пока нет.</Text>
          <Button component={Link} to="/" variant="light">
            Перейти к афише
          </Button>
        </Stack>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          {data?.map((order) => (
            <Card
              key={order.id}
              component={Link}
              to={`/orders/${order.id}`}
              withBorder
              radius="lg"
              padding="lg"
            >
              <Stack gap={6}>
                <Group justify="space-between">
                  <Badge color="teal" variant="light">
                    Оплачен
                  </Badge>
                  <Text size="xs" c="dimmed">
                    № {order.id.slice(-8).toUpperCase()}
                  </Text>
                </Group>
                <Text fw={700} size="lg">
                  {order.event_title}
                </Text>
                <Text size="sm" c="dimmed">
                  {formatDateTime(order.event_starts_at)}
                </Text>
                <Group justify="space-between" mt="xs">
                  <Text size="sm">
                    {order.tickets_count} {tickets(order.tickets_count)}
                  </Text>
                  <Text fw={700}>{formatPrice(order.total_kopecks)}</Text>
                </Group>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  )
}

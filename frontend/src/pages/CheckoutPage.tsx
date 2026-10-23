import {
  Alert,
  Anchor,
  Button,
  Center,
  Divider,
  Grid,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  Title,
  UnstyledButton,
} from '@mantine/core'
import { IconArrowLeft, IconCheck, IconLock, IconShieldCheck } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'

import { getMyHoldsQueryKey, useMyHolds } from '../api/generated/booking/booking'
import { useGetEvent } from '../api/generated/catalog/catalog'
import type { CheckoutOut } from '../api/generated/model'
import { useCheckout } from '../api/generated/orders/orders'
import { bookingErrorMessage } from '../features/booking/useBooking'
import { Countdown } from '../features/events/Countdown'
import { formatDateTime, formatPrice } from '../shared/format'
import classes from './CheckoutPage.module.css'

/** Тестовые карты банка-имитатора — как у реальных платёжных провайдеров. */
const TEST_CARDS = [
  {
    token: 'tok_ok',
    number: '4242 4242 4242 4242',
    title: 'Успешная оплата',
    hint: 'Банк подтвердит платёж',
    gradient: 'linear-gradient(135deg, #5f3dc4, #1c7ed6)',
  },
  {
    token: 'tok_decline',
    number: '4000 0000 0000 0002',
    title: 'Отказ банка',
    hint: 'Недостаточно средств — места освободятся',
    gradient: 'linear-gradient(135deg, #c92a2a, #e8590c)',
  },
  {
    token: 'tok_timeout',
    number: '4000 0000 0000 0119',
    title: 'Банк не отвечает',
    hint: 'Сбой связи с банком',
    gradient: 'linear-gradient(135deg, #343a40, #868e96)',
  },
] as const

const FAILURE_TEXT: Record<string, string> = {
  payment_declined: 'Банк отклонил платёж. Деньги не списаны, места освобождены.',
  payment_unavailable: 'Банк не ответил. Деньги не списаны, места освобождены.',
  seats_lost:
    'Пока шла оплата, время удержания мест истекло. Деньги возвращены, выберите места заново.',
  payment_not_confirmed: 'Платёж не подтвердился. Деньги не списаны, места освобождены.',
}

export function CheckoutPage() {
  const { eventId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const event = useGetEvent(eventId)
  const my = useMyHolds(eventId)
  const [token, setToken] = useState<string>('tok_ok')
  // Ключ идемпотентности — один на попытку оплаты: двойной клик не спишет деньги дважды.
  const [attemptKey, setAttemptKey] = useState(() => crypto.randomUUID())
  const [failed, setFailed] = useState<CheckoutOut | null>(null)
  const pay = useCheckout()

  if (event.isLoading || my.isLoading) {
    return (
      <Center py={80}>
        <Loader />
      </Center>
    )
  }
  if (!event.data) return <Navigate to="/" replace />

  const items = my.data?.items ?? []
  if (items.length === 0 && !failed && !pay.isPending) {
    return (
      <Stack align="center" py={80} gap="sm">
        <Title order={3}>Нет выбранных мест</Title>
        <Text c="dimmed">Удержание истекло или места ещё не выбраны.</Text>
        <Button component={Link} to={`/events/${eventId}`} variant="light">
          Выбрать места
        </Button>
      </Stack>
    )
  }

  const submit = async () => {
    setFailed(null)
    try {
      const result = await pay.mutateAsync({
        data: { event_id: eventId, payment_token: token },
        headers: { 'Idempotency-Key': attemptKey },
      })
      await queryClient.invalidateQueries({ queryKey: getMyHoldsQueryKey(eventId) })
      if (result.state === 'completed' && result.order_id) {
        navigate(`/orders/${result.order_id}?new=1`, { replace: true })
      } else {
        setFailed(result)
        setAttemptKey(crypto.randomUUID()) // следующая попытка — новый ключ
      }
    } catch {
      setAttemptKey(crypto.randomUUID())
    }
  }

  return (
    <Stack py="lg" gap="lg">
      <Anchor component={Link} to={`/events/${eventId}`} size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} /> К схеме зала
        </Group>
      </Anchor>
      <Title order={1}>Оплата</Title>

      <Grid gap="lg">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="md">
            {failed && (
              <Alert color="red" variant="light" title="Оплата не прошла">
                <Stack gap="xs">
                  <Text size="sm">{FAILURE_TEXT[failed.failure_reason ?? ''] ?? 'Ошибка оплаты.'}</Text>
                  <Anchor component={Link} to={`/events/${eventId}`} size="sm" fw={600}>
                    Вернуться к выбору мест →
                  </Anchor>
                </Stack>
              </Alert>
            )}
            {pay.error && (
              <Alert color="red" variant="light">
                {bookingErrorMessage(pay.error)}
              </Alert>
            )}

            <Paper withBorder radius="lg" p="lg">
              <Stack gap="md">
                <Group gap="xs">
                  <IconLock size={18} />
                  <Text fw={700}>Банковская карта</Text>
                </Group>
                <Text size="sm" c="dimmed">
                  Оплата учебная: деньги не списываются. Выберите тестовую карту — от неё
                  зависит ответ банка-имитатора.
                </Text>
                <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="sm">
                  {TEST_CARDS.map((card) => (
                    <UnstyledButton
                      key={card.token}
                      onClick={() => setToken(card.token)}
                      className={classes.card}
                      data-active={token === card.token || undefined}
                      style={{ background: card.gradient }}
                    >
                      <Group justify="space-between" align="flex-start">
                        <div className={classes.chip} />
                        {token === card.token && (
                          <ThemeIcon size="sm" radius="xl" color="white" c="dark">
                            <IconCheck size={14} />
                          </ThemeIcon>
                        )}
                      </Group>
                      <Text className={classes.cardNumber}>{card.number}</Text>
                      <Text size="sm" fw={700}>
                        {card.title}
                      </Text>
                      <Text size="xs" opacity={0.85}>
                        {card.hint}
                      </Text>
                    </UnstyledButton>
                  ))}
                </SimpleGrid>
              </Stack>
            </Paper>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder radius="lg" p="lg">
            <Stack gap="sm">
              <Text fw={700} size="lg">
                {event.data.title}
              </Text>
              <Text size="sm" c="dimmed">
                {formatDateTime(event.data.starts_at)} · {event.data.venue.name}
              </Text>
              <Divider />
              {items.map((item) => (
                <Group key={item.id} justify="space-between" wrap="nowrap">
                  <Text size="sm">
                    {item.section_name}
                    {item.standing ? ', стоячее место' : `, ряд ${item.row}, место ${item.number}`}
                  </Text>
                  <Text size="sm" fw={600}>
                    {formatPrice(item.price_kopecks)}
                  </Text>
                </Group>
              ))}
              <Divider />
              <Group justify="space-between">
                <Text fw={700}>К оплате</Text>
                <Text fw={800} size="xl">
                  {formatPrice(my.data?.total_kopecks ?? 0)}
                </Text>
              </Group>
              {my.data?.expires_at && (
                <Text size="xs" c="dimmed">
                  Места удерживаются ещё <Countdown to={my.data.expires_at} onDone={() => my.refetch()} />
                </Text>
              )}
              <Button size="lg" onClick={submit} loading={pay.isPending} disabled={items.length === 0}>
                {pay.isPending ? 'Связываемся с банком…' : `Оплатить ${formatPrice(my.data?.total_kopecks ?? 0)}`}
              </Button>
              <Group gap={6} justify="center" c="dimmed">
                <IconShieldCheck size={16} />
                <Text size="xs">Повторное нажатие не спишет деньги дважды</Text>
              </Group>
            </Stack>
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}

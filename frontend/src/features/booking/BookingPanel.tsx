import {
  ActionIcon,
  Badge,
  Button,
  Divider,
  Group,
  Paper,
  Progress,
  Stack,
  Text,
  ThemeIcon,
  Tooltip,
} from '@mantine/core'
import { IconClock, IconTicket, IconTrash, IconX } from '@tabler/icons-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import type { CategoryOut, HoldOut, MyHoldsOut } from '../../api/generated/model'
import { formatPrice } from '../../shared/format'
import { Countdown } from '../events/Countdown'

interface Line {
  key: string
  title: string
  subtitle: string
  categoryId: number
  price: number
  holdIds: string[]
}

function tickets(n: number): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return 'билет'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'билета'
  return 'билетов'
}

/** Билеты в одну стоячую зону показываем одной строкой «Танцпол × 3». */
function toLines(items: HoldOut[]): Line[] {
  const lines: Line[] = []
  const zones = new Map<number, Line>()
  for (const h of items) {
    if (h.standing) {
      const line = zones.get(h.section_id)
      if (line) {
        line.price += h.price_kopecks
        line.holdIds.push(h.id)
        line.subtitle = `${line.holdIds.length} ${tickets(line.holdIds.length)} · стоячие места`
      } else {
        const created: Line = {
          key: `zone-${h.section_id}`,
          title: h.section_name,
          subtitle: '1 билет · стоячие места',
          categoryId: h.category_id,
          price: h.price_kopecks,
          holdIds: [h.id],
        }
        zones.set(h.section_id, created)
        lines.push(created)
      }
    } else {
      lines.push({
        key: h.id,
        title: h.section_name,
        subtitle: `Ряд ${h.row}, место ${h.number}`,
        categoryId: h.category_id,
        price: h.price_kopecks,
        holdIds: [h.id],
      })
    }
  }
  return lines
}

function HoldTimer({ expiresAt, onExpired }: { expiresAt: string; onExpired: () => void }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const left = new Date(expiresAt).getTime() - now
  const total = 10 * 60 * 1000
  const urgent = left < 2 * 60 * 1000
  return (
    <Stack gap={6}>
      <Group gap={6} c={urgent ? 'red' : 'dimmed'}>
        <IconClock size={16} />
        <Text size="sm">
          Места держим ещё <Countdown to={expiresAt} onDone={onExpired} />
        </Text>
      </Group>
      <Progress
        value={Math.max(0, Math.min(100, (left / total) * 100))}
        color={urgent ? 'red' : 'teal'}
        size="xs"
        animated={urgent}
      />
    </Stack>
  )
}

export function BookingPanel({
  eventId,
  my,
  categories,
  busy,
  onRelease,
  onReleaseAll,
  onExpired,
}: {
  eventId: string
  my: MyHoldsOut | undefined
  categories: Map<number, CategoryOut>
  busy: boolean
  onRelease: (holdId: string) => void
  onReleaseAll: () => void
  onExpired: () => void
}) {
  const items = my?.items ?? []
  const lines = toLines(items)

  return (
    <Paper withBorder radius="md" p="lg" pos="sticky" top={76}>
      <Stack gap="md">
        <Group justify="space-between">
          <Group gap="xs">
            <ThemeIcon variant="light" radius="xl">
              <IconTicket size={18} />
            </ThemeIcon>
            <Text fw={700}>Ваш выбор</Text>
          </Group>
          {my && (
            <Badge variant="light" color={items.length >= my.limit ? 'orange' : 'gray'}>
              {items.length} из {my.limit}
            </Badge>
          )}
        </Group>

        {lines.length === 0 ? (
          <Text size="sm" c="dimmed">
            Нажмите на свободное место на схеме или на стоячую зону. Место удерживается за вами
            10 минут — успейте оформить заказ.
          </Text>
        ) : (
          <>
            {my?.expires_at && <HoldTimer expiresAt={my.expires_at} onExpired={onExpired} />}
            <Stack gap="xs">
              {lines.map((line) => (
                <Group key={line.key} justify="space-between" wrap="nowrap" align="flex-start">
                  <Group gap="sm" wrap="nowrap" align="flex-start">
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        marginTop: 6,
                        borderRadius: 5,
                        flex: 'none',
                        background: categories.get(line.categoryId)?.color,
                      }}
                    />
                    <div>
                      <Text size="sm" fw={600}>
                        {line.title}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {line.subtitle}
                        {line.key.startsWith('zone-')
                          ? ''
                          : ` · ${categories.get(line.categoryId)?.name}`}
                      </Text>
                    </div>
                  </Group>
                  <Group gap={4} wrap="nowrap">
                    <Text size="sm" fw={600}>
                      {formatPrice(line.price)}
                    </Text>
                    <Tooltip label={line.holdIds.length > 1 ? 'Убрать один билет' : 'Убрать'}>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        size="sm"
                        disabled={busy}
                        onClick={() => onRelease(line.holdIds[line.holdIds.length - 1])}
                        aria-label="Убрать"
                      >
                        <IconX size={14} />
                      </ActionIcon>
                    </Tooltip>
                  </Group>
                </Group>
              ))}
            </Stack>
            <Divider />
            <Group justify="space-between">
              <Text fw={700}>Итого</Text>
              <Text fw={800} size="lg">
                {formatPrice(my?.total_kopecks ?? 0)}
              </Text>
            </Group>
            <Button size="md" fullWidth component={Link} to={`/checkout/${eventId}`}>
              Перейти к оплате
            </Button>
            <Button
              variant="subtle"
              color="gray"
              leftSection={<IconTrash size={16} />}
              onClick={onReleaseAll}
              disabled={busy}
            >
              Очистить выбор
            </Button>
          </>
        )}
      </Stack>
    </Paper>
  )
}

import { ActionIcon, Indicator, Popover, ScrollArea, Stack, Text, ThemeIcon, UnstyledButton } from '@mantine/core'
import { IconBell, IconCircleCheck, IconCircleX } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import {
  getMyNotificationsQueryKey,
  useMarkNotificationsRead,
  useMyNotifications,
} from '../../api/generated/notifications/notifications'
import classes from './NotificationBell.module.css'

const timeFormat = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

/** Колокольчик: уведомления приходят от фонового воркера (событие → RabbitMQ → обработчик). */
export function NotificationBell() {
  const [opened, setOpened] = useState(false)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data } = useMyNotifications({ query: { refetchInterval: 20_000 } })
  const markRead = useMarkNotificationsRead({
    mutation: {
      onSuccess: () => queryClient.invalidateQueries({ queryKey: getMyNotificationsQueryKey() }),
    },
  })

  const unread = data?.unread ?? 0

  const toggle = () => {
    const next = !opened
    setOpened(next)
    if (next && unread > 0) markRead.mutate()
  }

  return (
    <Popover opened={opened} onChange={setOpened} position="bottom-end" width={340} shadow="lg">
      <Popover.Target>
        <Indicator label={unread} size={16} disabled={unread === 0} offset={4} color="red">
          <ActionIcon variant="subtle" color="gray" size="lg" onClick={toggle} aria-label="Уведомления">
            <IconBell size={20} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <Text fw={700} px="md" pt="sm" pb="xs">
          Уведомления
        </Text>
        {!data?.items.length ? (
          <Text size="sm" c="dimmed" px="md" pb="md">
            Пока пусто. Здесь появятся сообщения об оплате и билетах.
          </Text>
        ) : (
          <ScrollArea.Autosize mah={360}>
            <Stack gap={0}>
              {data.items.map((n) => (
                <UnstyledButton
                  key={n.id}
                  className={classes.item}
                  data-unread={!n.read || undefined}
                  onClick={() => {
                    setOpened(false)
                    if (n.link) navigate(n.link)
                  }}
                >
                  <ThemeIcon
                    variant="light"
                    radius="xl"
                    color={n.kind === 'order_paid' ? 'teal' : 'red'}
                  >
                    {n.kind === 'order_paid' ? (
                      <IconCircleCheck size={18} />
                    ) : (
                      <IconCircleX size={18} />
                    )}
                  </ThemeIcon>
                  <div>
                    <Text size="sm" fw={600}>
                      {n.title}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {n.body}
                    </Text>
                    <Text size="xs" c="dimmed" mt={2}>
                      {timeFormat.format(new Date(n.created_at))}
                    </Text>
                  </div>
                </UnstyledButton>
              ))}
            </Stack>
          </ScrollArea.Autosize>
        )}
      </Popover.Dropdown>
    </Popover>
  )
}

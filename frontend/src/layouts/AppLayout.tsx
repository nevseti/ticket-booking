import { Anchor, AppShell, Badge, Container, Group, Text, Title } from '@mantine/core'
import { IconTicket } from '@tabler/icons-react'
import { Link, NavLink, Outlet } from 'react-router'

import { useHealth } from '../api/generated/system/system'
import { UserMenu } from '../features/auth/UserMenu'
import { NotificationBell } from '../features/notifications/NotificationBell'
import { useCurrentUser } from '../features/auth/useCurrentUser'

function ApiStatus() {
  const { data, isError } = useHealth({ query: { refetchInterval: 30_000, retry: false } })
  if (isError) return <Badge color="red" variant="light">API недоступно</Badge>
  if (!data) return null
  return (
    <Text size="xs" c="dimmed">
      API {data.version} · {data.env}
    </Text>
  )
}

export function AppLayout() {
  const { isAdmin, user } = useCurrentUser()
  return (
    <AppShell header={{ height: 60 }} footer={{ height: 36 }} padding="md">
      <AppShell.Header>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between">
            <Anchor component={Link} to="/" underline="never" c="inherit">
              <Group gap={8}>
                <IconTicket size={26} stroke={1.8} color="var(--mantine-primary-color-filled)" />
                <Title order={4}>Билеты</Title>
              </Group>
            </Anchor>
            <Group gap="lg">
              <Anchor component={NavLink} to="/" size="sm">
                Афиша
              </Anchor>
              {isAdmin && (
                <Anchor component={NavLink} to="/admin/events" size="sm">
                  Админка
                </Anchor>
              )}
              {user && <NotificationBell />}
              <UserMenu />
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="lg">
          <Outlet />
        </Container>
      </AppShell.Main>

      <AppShell.Footer>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between">
            <Text size="xs" c="dimmed">
              Учебный проект: мероприятия вымышленные, оплата — имитация
            </Text>
            <ApiStatus />
          </Group>
        </Container>
      </AppShell.Footer>
    </AppShell>
  )
}

import { Anchor, AppShell, Badge, Container, Group, Text, Title } from '@mantine/core'
import { IconTicket } from '@tabler/icons-react'
import { Link, NavLink, Outlet } from 'react-router'

import { useHealth } from '../api/system'

function ApiStatus() {
  const { data, isError } = useHealth()
  if (isError) return <Badge color="red" variant="light">API недоступно</Badge>
  if (!data) return null
  return (
    <Text size="xs" c="dimmed">
      API {data.version} · {data.env}
    </Text>
  )
}

export function AppLayout() {
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
              Курсовая · Архитектура клиент-серверных приложений
            </Text>
            <ApiStatus />
          </Group>
        </Container>
      </AppShell.Footer>
    </AppShell>
  )
}

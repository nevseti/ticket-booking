import { Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'

import { useCurrentUser } from '../features/auth/useCurrentUser'

export function ProfilePage() {
  const { user } = useCurrentUser()
  if (!user) return null

  return (
    <Stack maw={560} py="xl">
      <Title order={2}>Профиль</Title>
      <Paper withBorder p="lg">
        <Stack gap="xs">
          <Group gap="xs">
            <Text fw={600}>{user.name}</Text>
            {user.role === 'admin' && <Badge variant="light">администратор</Badge>}
          </Group>
          <Text c="dimmed">{user.email}</Text>
          <Text size="sm" c="dimmed">
            С нами с {new Date(user.created_at).toLocaleDateString('ru-RU')}
          </Text>
        </Stack>
      </Paper>
    </Stack>
  )
}

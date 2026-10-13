import { Stack, Text, Title } from '@mantine/core'

export function HomePage() {
  return (
    <Stack gap="xs" py="xl">
      <Title order={1}>Афиша</Title>
      <Text c="dimmed">Концерты, спектакли и спортивные события на одной площадке.</Text>
      <Text c="dimmed" size="sm">
        Список мероприятий появится вместе с модулем каталога.
      </Text>
    </Stack>
  )
}

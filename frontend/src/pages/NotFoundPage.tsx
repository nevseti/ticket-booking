import { Button, Stack, Text, Title } from '@mantine/core'
import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <Stack align="center" gap="sm" py={80}>
      <Title order={2}>Страница не найдена</Title>
      <Text c="dimmed">Возможно, ссылка устарела.</Text>
      <Button component={Link} to="/" variant="light">
        На главную
      </Button>
    </Stack>
  )
}

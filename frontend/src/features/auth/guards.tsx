import { Center, Loader, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'

import { useCurrentUser } from './useCurrentUser'

function FullPageLoader() {
  return (
    <Center py={80}>
      <Loader />
    </Center>
  )
}

/** Пускает только вошедших; гостя отправляет на /login и возвращает обратно после входа. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useCurrentUser()
  const location = useLocation()

  if (isLoading) return <FullPageLoader />
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return <Navigate to={`/login?next=${next}`} replace />
  }
  return children
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { isAdmin } = useCurrentUser()
  if (!isAdmin) {
    return (
      <Stack align="center" py={80} gap="xs">
        <Title order={3}>Нет доступа</Title>
        <Text c="dimmed">Раздел доступен только администраторам.</Text>
      </Stack>
    )
  }
  return children
}

/** Гостя — на вход, обычного пользователя — на «нет доступа». */
export function RequireAdmin({ children }: { children: ReactNode }) {
  return (
    <RequireAuth>
      <AdminOnly>{children}</AdminOnly>
    </RequireAuth>
  )
}

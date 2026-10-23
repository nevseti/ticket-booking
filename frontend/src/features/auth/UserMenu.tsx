import { Avatar, Button, Menu, Skeleton, UnstyledButton } from '@mantine/core'
import { IconLogout, IconTicket, IconUser } from '@tabler/icons-react'
import { Link, useLocation, useNavigate } from 'react-router'

import { useCurrentUser, useSignOut } from './useCurrentUser'

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export function UserMenu() {
  const { user, isLoading } = useCurrentUser()
  const signOut = useSignOut()
  const navigate = useNavigate()
  const location = useLocation()

  if (isLoading) return <Skeleton circle height={32} />

  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search)
    return (
      <Button component={Link} to={`/login?next=${next}`} variant="light" size="xs">
        Войти
      </Button>
    )
  }

  return (
    <Menu position="bottom-end" width={200} withinPortal>
      <Menu.Target>
        <UnstyledButton aria-label="Меню пользователя">
          <Avatar color="violet" radius="xl" size={32}>
            {initials(user.name)}
          </Avatar>
        </UnstyledButton>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>{user.email}</Menu.Label>
        <Menu.Item component={Link} to="/orders" leftSection={<IconTicket size={16} />}>
          Мои заказы
        </Menu.Item>
        <Menu.Item component={Link} to="/profile" leftSection={<IconUser size={16} />}>
          Профиль
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item
          color="red"
          leftSection={<IconLogout size={16} />}
          onClick={async () => {
            await signOut()
            navigate('/')
          }}
        >
          Выйти
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}

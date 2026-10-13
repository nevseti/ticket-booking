import {
  ActionIcon,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Menu,
  Pagination,
  SegmentedControl,
  Stack,
  Table,
  Text,
  Title,
} from '@mantine/core'
import { modals } from '@mantine/modals'
import { notifications } from '@mantine/notifications'
import { IconDots, IconEdit, IconExternalLink, IconPlus, IconSend, IconX } from '@tabler/icons-react'
import { keepPreviousData, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'

import {
  useAdminCancelEvent,
  useAdminListEvents,
  useAdminPublishEvent,
} from '../../api/generated/catalog-admin/catalog-admin'
import type { AdminEvent, EventStatus } from '../../api/generated/model'
import { invalidateCatalog } from '../../features/admin/invalidate'
import { formatPrice, formatShortDateTime, KIND_LABELS, SALE_STATUS } from '../../shared/format'

const PAGE_SIZE = 20
const STATUS_FILTERS = [
  { value: 'all', label: 'Все' },
  { value: 'draft', label: 'Черновики' },
  { value: 'published', label: 'Опубликованы' },
  { value: 'cancelled', label: 'Отменены' },
]

function EventActions({ event }: { event: AdminEvent }) {
  const queryClient = useQueryClient()
  const publish = useAdminPublishEvent()
  const cancel = useAdminCancelEvent()

  const onPublish = async () => {
    try {
      await publish.mutateAsync({ eventId: event.id })
      notifications.show({ color: 'teal', message: `«${event.title}» опубликовано` })
    } catch (error) {
      notifications.show({ color: 'red', message: (error as Error).message })
    } finally {
      await invalidateCatalog(queryClient)
    }
  }

  const onCancel = () =>
    modals.openConfirmModal({
      title: 'Отменить мероприятие?',
      children: <Text size="sm">Продажи прекратятся. Действие необратимо.</Text>,
      labels: { confirm: 'Отменить мероприятие', cancel: 'Назад' },
      confirmProps: { color: 'red' },
      onConfirm: async () => {
        await cancel.mutateAsync({ eventId: event.id })
        await invalidateCatalog(queryClient)
        notifications.show({ message: `«${event.title}» отменено` })
      },
    })

  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <ActionIcon variant="subtle" color="gray" aria-label="Действия">
          <IconDots size={16} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={Link} to={`/admin/events/${event.id}`} leftSection={<IconEdit size={14} />}>
          Редактировать
        </Menu.Item>
        <Menu.Item component={Link} to={`/events/${event.id}`} leftSection={<IconExternalLink size={14} />}>
          Открыть на сайте
        </Menu.Item>
        {event.status === 'draft' && (
          <Menu.Item leftSection={<IconSend size={14} />} onClick={onPublish}>
            Опубликовать
          </Menu.Item>
        )}
        {event.status === 'published' && (
          <Menu.Item color="red" leftSection={<IconX size={14} />} onClick={onCancel}>
            Отменить
          </Menu.Item>
        )}
      </Menu.Dropdown>
    </Menu>
  )
}

export function AdminEventsPage() {
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const { data, isLoading } = useAdminListEvents(
    {
      status: status === 'all' ? undefined : (status as EventStatus),
      page,
      page_size: PAGE_SIZE,
    },
    { query: { placeholderData: keepPreviousData } },
  )
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <Stack py="lg">
      <Group justify="space-between">
        <Title order={2}>Мероприятия</Title>
        <Button component={Link} to="/admin/events/new" leftSection={<IconPlus size={16} />}>
          Новое мероприятие
        </Button>
      </Group>
      <SegmentedControl
        data={STATUS_FILTERS}
        value={status}
        onChange={(value) => {
          setStatus(value)
          setPage(1)
        }}
        w="fit-content"
      />

      {isLoading ? (
        <Center py="xl">
          <Loader />
        </Center>
      ) : (
        <Table.ScrollContainer minWidth={760}>
          <Table striped highlightOnHover verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Название</Table.Th>
                <Table.Th>Тип</Table.Th>
                <Table.Th>Начало</Table.Th>
                <Table.Th>Продажи</Table.Th>
                <Table.Th>Цена от</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data?.items.map((event) => {
                const sale = SALE_STATUS[event.sale_status]
                return (
                  <Table.Tr key={event.id}>
                    <Table.Td>
                      <Text component={Link} to={`/admin/events/${event.id}`} fw={600} size="sm">
                        {event.title}
                      </Text>
                    </Table.Td>
                    <Table.Td>{KIND_LABELS[event.kind]}</Table.Td>
                    <Table.Td>{formatShortDateTime(event.starts_at)}</Table.Td>
                    <Table.Td>
                      <Badge variant="light" color={sale.color}>
                        {sale.label}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {event.min_price_kopecks != null ? formatPrice(event.min_price_kopecks) : '—'}
                    </Table.Td>
                    <Table.Td>
                      <EventActions event={event} />
                    </Table.Td>
                  </Table.Tr>
                )
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {data?.items.length === 0 && (
        <Text c="dimmed" ta="center">
          Мероприятий пока нет
        </Text>
      )}
      {pages > 1 && <Pagination total={pages} value={page} onChange={setPage} />}
    </Stack>
  )
}

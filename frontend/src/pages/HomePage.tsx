import {
  Center,
  Group,
  Loader,
  Pagination,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconSearch } from '@tabler/icons-react'
import { keepPreviousData } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import { useListEvents } from '../api/generated/catalog/catalog'
import type { EventKind } from '../api/generated/model'
import { EventCard } from '../features/events/EventCard'

const PAGE_SIZE = 12
const KIND_FILTERS = [
  { value: 'all', label: 'Все' },
  { value: 'concert', label: 'Концерты' },
  { value: 'theatre', label: 'Театр' },
  { value: 'sport', label: 'Спорт' },
  { value: 'show', label: 'Шоу' },
]

export function HomePage() {
  // Фильтры живут в URL: ссылкой на отфильтрованную афишу можно поделиться.
  const [params, setParams] = useSearchParams()
  const kind = params.get('kind') ?? 'all'
  const page = Number(params.get('page') ?? '1') || 1
  const [search, setSearch] = useState(params.get('q') ?? '')
  const [debouncedSearch] = useDebouncedValue(search.trim(), 300)

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value)
      else next.delete(key)
    }
    setParams(next, { replace: true })
  }

  useEffect(() => {
    if ((params.get('q') ?? '') !== debouncedSearch) {
      update({ q: debouncedSearch || null, page: null })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- синхронизация только по вводу
  }, [debouncedSearch])

  const { data, isLoading, isError } = useListEvents(
    {
      kind: kind === 'all' ? undefined : (kind as EventKind),
      q: params.get('q') || undefined,
      page,
      page_size: PAGE_SIZE,
    },
    { query: { placeholderData: keepPreviousData } },
  )

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <Stack gap="lg" py="lg">
      <div>
        <Title order={1}>Афиша</Title>
        <Text c="dimmed">Концерты, спектакли и спортивные события на одной площадке.</Text>
      </div>

      <Group justify="space-between" wrap="wrap">
        <SegmentedControl
          data={KIND_FILTERS}
          value={kind}
          onChange={(value) => update({ kind: value === 'all' ? null : value, page: null })}
        />
        <TextInput
          placeholder="Поиск по названию"
          leftSection={<IconSearch size={16} />}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
          w={{ base: '100%', sm: 280 }}
        />
      </Group>

      {isLoading && (
        <Center py="xl">
          <Loader />
        </Center>
      )}
      {isError && <Text c="red">Не удалось загрузить афишу. Попробуйте обновить страницу.</Text>}
      {data && data.items.length === 0 && (
        <Text c="dimmed" ta="center" py="xl">
          Ничего не нашлось. Попробуйте изменить фильтры.
        </Text>
      )}

      {data && data.items.length > 0 && (
        <SimpleGrid cols={{ base: 1, xs: 2, md: 3, lg: 4 }} spacing="lg">
          {data.items.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </SimpleGrid>
      )}

      {pages > 1 && (
        <Center>
          <Pagination
            total={pages}
            value={page}
            onChange={(p) => update({ page: p === 1 ? null : String(p) })}
          />
        </Center>
      )}
    </Stack>
  )
}

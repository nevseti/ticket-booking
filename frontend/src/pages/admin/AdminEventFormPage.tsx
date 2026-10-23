import {
  Alert,
  Anchor,
  Badge,
  Button,
  Center,
  Grid,
  Group,
  Loader,
  NumberInput,
  Paper,
  Select,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { DateTimePicker } from '@mantine/dates'
import { useForm } from '@mantine/form'
import { notifications } from '@mantine/notifications'
import { IconArrowLeft } from '@tabler/icons-react'
import { useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { useEffect } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import {
  useAdminCreateEvent,
  useAdminGetEvent,
  useAdminPublishEvent,
  useAdminUpdateEvent,
} from '../../api/generated/catalog-admin/catalog-admin'
import type { AdminEvent, EventIn, EventKind } from '../../api/generated/model'
import { ApiError } from '../../api/http'
import { invalidateCatalog } from '../../features/admin/invalidate'
import { useVenueLayout } from '../../features/seatmap/useVenueLayout'
import { KIND_LABELS, SALE_STATUS } from '../../shared/format'

const PICKER_FORMAT = 'YYYY-MM-DD HH:mm:ss'

interface FormValues {
  title: string
  kind: EventKind
  description: string
  starts_at: string | null
  sales_start_at: string | null
  sales_end_at: string | null
  poster_url: string
  poster_credit: string
  poster_source: string
  prices: Record<string, number | string>
}

const toPicker = (iso: string | null | undefined) => (iso ? dayjs(iso).format(PICKER_FORMAT) : null)
// Значение пикера — локальное время без пояса; на сервер уходит ISO 8601 в UTC.
const fromPicker = (value: string | null) => (value ? dayjs(value).toISOString() : null)

function toFormValues(event: AdminEvent): FormValues {
  return {
    title: event.title,
    kind: event.kind,
    description: event.description,
    starts_at: toPicker(event.starts_at),
    sales_start_at: toPicker(event.sales_start_at),
    sales_end_at: toPicker(event.sales_end_at),
    poster_url: event.poster_url ?? '',
    poster_credit: event.poster_credit ?? '',
    poster_source: event.poster_source ?? '',
    prices: Object.fromEntries(event.prices.map((p) => [p.category_id, p.price_kopecks / 100])),
  }
}

/** Режим зала по типу мероприятия — то же правило, что на сервере (catalog.service). */
const hallConfigFor = (kind: EventKind) => (kind === 'sport' ? 'hockey' : 'stage')

function toPayload(values: FormValues, allowed: Set<number>): EventIn {
  return {
    title: values.title,
    kind: values.kind,
    description: values.description,
    starts_at: fromPicker(values.starts_at) ?? '',
    sales_start_at: fromPicker(values.sales_start_at) ?? '',
    sales_end_at: fromPicker(values.sales_end_at),
    poster_url: values.poster_url.trim() || null,
    poster_credit: values.poster_credit.trim() || null,
    poster_source: values.poster_source.trim() || null,
    prices: Object.entries(values.prices)
      // Цены категорий, которых нет в режиме зала (например, танцпол на хоккее), не отправляем.
      .filter(([category]) => allowed.has(Number(category)))
      .filter(([, rub]) => typeof rub === 'number' && rub > 0)
      .map(([category, rub]) => ({
        category_id: Number(category),
        price_kopecks: Math.round(Number(rub) * 100),
      })),
  }
}

/** Сообщения об ошибках валидации сервера, включая ошибки уровня всей формы. */
function serverMessages(error: unknown): string[] {
  if (!(error instanceof ApiError)) return []
  const items = error.problem.errors as { msg: string }[] | undefined
  if (!items?.length) return [error.message]
  return items.map((e) => e.msg.replace(/^Value error, /, ''))
}

export function AdminEventFormPage() {
  const { eventId } = useParams()
  const isNew = !eventId
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const layout = useVenueLayout()
  const existing = useAdminGetEvent(eventId ?? '', { query: { enabled: !isNew } })
  const create = useAdminCreateEvent()
  const update = useAdminUpdateEvent()
  const publish = useAdminPublishEvent()

  const form = useForm<FormValues>({
    initialValues: {
      title: '',
      kind: 'concert',
      description: '',
      starts_at: null,
      sales_start_at: null,
      sales_end_at: null,
      poster_url: '',
      poster_credit: '',
      poster_source: '',
      prices: {},
    },
    validate: {
      title: (v) => (v.trim() ? null : 'Введите название'),
      starts_at: (v) => (v ? null : 'Укажите дату начала'),
      sales_start_at: (v) => (v ? null : 'Укажите начало продаж'),
    },
  })

  const event = existing.data
  useEffect(() => {
    if (event) {
      form.setValues(toFormValues(event))
      form.resetDirty()
    }
    // форма заполняется один раз при загрузке мероприятия
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [event?.id, event?.updated_at])

  const saving = create.isPending || update.isPending
  const error = create.error ?? update.error ?? publish.error

  const hallConfig = layout.data?.hall_configs.find(
    (c) => c.id === hallConfigFor(form.values.kind),
  )
  const allowedCategories = new Set(hallConfig?.category_ids ?? [])

  const submit = form.onSubmit(async (values) => {
    const data = toPayload(values, allowedCategories)
    try {
      if (isNew) {
        const created = await create.mutateAsync({ data })
        notifications.show({ color: 'teal', message: 'Черновик создан' })
        navigate(`/admin/events/${created.id}`, { replace: true })
      } else {
        await update.mutateAsync({ eventId, data })
        notifications.show({ color: 'teal', message: 'Изменения сохранены' })
      }
    } catch {
      // ошибки показываются в Alert над формой
    } finally {
      await invalidateCatalog(queryClient)
    }
  })

  const onPublish = async () => {
    if (!eventId) return
    try {
      await publish.mutateAsync({ eventId })
      notifications.show({ color: 'teal', message: 'Мероприятие опубликовано' })
    } catch {
      // показывается в Alert
    } finally {
      await invalidateCatalog(queryClient)
    }
  }

  if (!isNew && existing.isLoading) {
    return (
      <Center py={80}>
        <Loader />
      </Center>
    )
  }

  return (
    <Stack py="lg" maw={860}>
      <Anchor component={Link} to="/admin/events" size="sm">
        <Group gap={4}>
          <IconArrowLeft size={14} /> Все мероприятия
        </Group>
      </Anchor>
      <Group justify="space-between">
        <Title order={2}>{isNew ? 'Новое мероприятие' : 'Редактирование'}</Title>
        {event && (
          <Badge size="lg" variant="light" color={SALE_STATUS[event.sale_status].color}>
            {SALE_STATUS[event.sale_status].label}
          </Badge>
        )}
      </Group>

      {error && (
        <Alert color="red" variant="light" title="Не удалось сохранить">
          {serverMessages(error).map((msg) => (
            <div key={msg}>{msg}</div>
          ))}
        </Alert>
      )}

      <form onSubmit={submit}>
        <Stack>
          <Paper withBorder p="lg">
            <Stack>
              <TextInput label="Название" required {...form.getInputProps('title')} />
              <Select
                label="Тип"
                data={Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label }))}
                allowDeselect={false}
                {...form.getInputProps('kind')}
              />
              <Textarea label="Описание" autosize minRows={3} {...form.getInputProps('description')} />
              <TextInput
                label="Ссылка на постер"
                description="Ссылка https://… или путь на сайте /posters/… Без постера — генерируемая афиша"
                placeholder="https://..."
                {...form.getInputProps('poster_url')}
              />
              <Grid>
                <Grid.Col span={{ base: 12, sm: 6 }}>
                  <TextInput
                    label="Автор фото и лицензия"
                    description="Для фото со свободной лицензией (CC BY, CC BY-SA)"
                    placeholder="Фото: Автор, CC BY-SA 4.0, Wikimedia Commons"
                    {...form.getInputProps('poster_credit')}
                  />
                </Grid.Col>
                <Grid.Col span={{ base: 12, sm: 6 }}>
                  <TextInput
                    label="Страница фото"
                    placeholder="https://commons.wikimedia.org/wiki/File:..."
                    {...form.getInputProps('poster_source')}
                  />
                </Grid.Col>
              </Grid>
            </Stack>
          </Paper>

          <Paper withBorder p="lg">
            <Grid>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                <DateTimePicker label="Начало мероприятия" required {...form.getInputProps('starts_at')} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                <DateTimePicker label="Старт продаж" required {...form.getInputProps('sales_start_at')} />
              </Grid.Col>
              <Grid.Col span={{ base: 12, sm: 4 }}>
                <DateTimePicker
                  label="Конец продаж"
                  description="По умолчанию — начало мероприятия"
                  clearable
                  {...form.getInputProps('sales_end_at')}
                />
              </Grid.Col>
            </Grid>
          </Paper>

          <Paper withBorder p="lg">
            <Text fw={600} mb="sm">
              Цены по категориям, ₽
            </Text>
            <Grid>
              {layout.data?.categories
                .filter((category) => allowedCategories.has(category.id))
                .map((category) => (
                <Grid.Col key={category.id} span={{ base: 6, sm: 3 }}>
                  <NumberInput
                    label={
                      <Group gap={6} component="span">
                        <span
                          style={{ width: 10, height: 10, borderRadius: 5, background: category.color }}
                        />
                        {category.name}
                      </Group>
                    }
                    min={1}
                    max={100000}
                    thousandSeparator=" "
                    {...form.getInputProps(`prices.${category.id}`)}
                  />
                </Grid.Col>
              ))}
            </Grid>
            <Text size="xs" c="dimmed" mt="xs">
              {hallConfig?.name}. Для публикации нужны цены во всех категориях этого режима.
            </Text>
          </Paper>

          <Group>
            <Button type="submit" loading={saving}>
              {isNew ? 'Создать черновик' : 'Сохранить'}
            </Button>
            {event?.status === 'draft' && (
              <Button variant="light" color="teal" onClick={onPublish} loading={publish.isPending}>
                Опубликовать
              </Button>
            )}
            {event && (
              <Button component={Link} to={`/events/${event.id}`} variant="subtle">
                Открыть на сайте
              </Button>
            )}
          </Group>
        </Stack>
      </form>
    </Stack>
  )
}

import { Button, Group, Modal, NumberInput, Stack, Text } from '@mantine/core'
import { useState } from 'react'

import type { SectionOut } from '../../api/generated/model'
import { formatPrice } from '../../shared/format'

/** Выбор количества билетов в стоячую зону (Фан-зона, Танцпол). */
export function ZoneModal({
  zone,
  price,
  available,
  canAdd,
  loading,
  onClose,
  onConfirm,
}: {
  zone: SectionOut | null
  price: number | undefined
  available: number
  canAdd: number
  loading: boolean
  onClose: () => void
  onConfirm: (quantity: number) => void
}) {
  const max = Math.max(0, Math.min(available, canAdd))
  // Количество сбрасывается при открытии другой зоны: родитель пересоздаёт окно по key.
  const [quantity, setQuantity] = useState(1)

  return (
    <Modal opened={zone !== null} onClose={onClose} title={zone?.name} centered radius="md">
      <Stack>
        <Text size="sm" c="dimmed">
          Стоячие места без номера: проходите в зону и выбираете место сами. Свободно{' '}
          {available} из {zone?.capacity}.
        </Text>
        {max === 0 ? (
          <Text c="red" size="sm">
            {available === 0
              ? 'Билеты в эту зону закончились.'
              : 'Вы уже выбрали максимум билетов на мероприятие.'}
          </Text>
        ) : (
          <>
            <NumberInput
              label="Количество билетов"
              min={1}
              max={max}
              value={quantity}
              onChange={(v) => setQuantity(Number(v) || 1)}
              clampBehavior="strict"
              allowDecimal={false}
            />
            <Group justify="space-between">
              <Text c="dimmed">Итого</Text>
              <Text fw={700} size="lg">
                {price != null ? formatPrice(price * quantity) : '—'}
              </Text>
            </Group>
          </>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button disabled={max === 0} loading={loading} onClick={() => onConfirm(quantity)}>
            Выбрать
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

import { ActionIcon, Group } from '@mantine/core'
import { IconFocusCentered, IconMinus, IconPlus } from '@tabler/icons-react'
import { memo, useCallback, useMemo, useRef, useState } from 'react'
import type { MouseEvent } from 'react'
import { TransformComponent, TransformWrapper } from 'react-zoom-pan-pinch'

import type { SeatOut, VenueLayout } from '../../api/generated/model'
import { formatPrice } from '../../shared/format'
import classes from './SeatMap.module.css'

const SEAT_RADIUS = 6

export interface SeatMapProps {
  layout: VenueLayout
  /** Цены мероприятия: id категории → копейки. Без них подсказка показывает только место. */
  prices?: Map<number, number>
}

interface Hovered {
  seat: SeatOut
  left: number
  top: number
}

/**
 * Статичная часть схемы: сцена, секторы, места. Мемоизирована целиком — при наведении
 * курсора и прочих перерисовках родителя 2–3 тысячи элементов SVG не пересоздаются.
 */
const SeatLayer = memo(function SeatLayer({ layout }: { layout: VenueLayout }) {
  const colors = useMemo(
    () => new Map(layout.categories.map((c) => [c.id, c.color])),
    [layout.categories],
  )
  const stageX = layout.width / 2
  return (
    <>
      <path d={layout.stage_path} className={classes.stage} />
      <text x={stageX} y={62} className={classes.stageLabel}>
        СЦЕНА
      </text>
      {layout.sections.map((section) => (
        <g key={section.id}>
          <path d={section.path} className={classes.section} />
          <text x={section.label_x} y={section.label_y} className={classes.sectionLabel}>
            {section.name}
          </text>
        </g>
      ))}
      <g>
        {layout.seats.map((seat) => (
          <circle
            key={seat.id}
            data-seat-id={seat.id}
            cx={seat.x}
            cy={seat.y}
            r={SEAT_RADIUS}
            fill={colors.get(seat.category_id)}
            className={classes.seat}
          />
        ))}
      </g>
    </>
  )
})

export function SeatMap({ layout, prices }: SeatMapProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const [hovered, setHovered] = useState<Hovered | null>(null)

  const seatsById = useMemo(() => new Map(layout.seats.map((s) => [s.id, s])), [layout.seats])
  const sectionsById = useMemo(
    () => new Map(layout.sections.map((s) => [s.id, s])),
    [layout.sections],
  )
  const categoriesById = useMemo(
    () => new Map(layout.categories.map((c) => [c.id, c])),
    [layout.categories],
  )

  // Один обработчик на весь SVG (делегирование) вместо тысяч обработчиков на местах.
  const handleMouseOver = useCallback(
    (e: MouseEvent<SVGSVGElement>) => {
      const target = e.target as Element
      const id = target.getAttribute('data-seat-id')
      const seat = id ? seatsById.get(Number(id)) : undefined
      const wrapper = wrapperRef.current
      if (!seat || !wrapper) {
        setHovered(null)
        return
      }
      const seatBox = target.getBoundingClientRect()
      const box = wrapper.getBoundingClientRect()
      setHovered({
        seat,
        left: seatBox.left + seatBox.width / 2 - box.left,
        top: seatBox.top - box.top,
      })
    },
    [seatsById],
  )

  const hoveredPrice = hovered ? prices?.get(hovered.seat.category_id) : undefined

  return (
    <div ref={wrapperRef} className={classes.wrapper} onMouseLeave={() => setHovered(null)}>
      <TransformWrapper
        minScale={1}
        maxScale={6}
        wheel={{ step: 0.15 }}
        doubleClick={{ mode: 'zoomIn', step: 0.7 }}
        onTransform={() => setHovered(null)}
      >
        {({ zoomIn, zoomOut, resetTransform }) => (
          <>
            <Group gap={4} className={classes.controls}>
              <ActionIcon variant="default" aria-label="Приблизить" onClick={() => zoomIn()}>
                <IconPlus size={16} />
              </ActionIcon>
              <ActionIcon variant="default" aria-label="Отдалить" onClick={() => zoomOut()}>
                <IconMinus size={16} />
              </ActionIcon>
              <ActionIcon
                variant="default"
                aria-label="Показать весь зал"
                onClick={() => resetTransform()}
              >
                <IconFocusCentered size={16} />
              </ActionIcon>
            </Group>
            <TransformComponent wrapperStyle={{ width: '100%' }} contentStyle={{ width: '100%' }}>
              <svg
                viewBox={`0 0 ${layout.width} ${layout.height}`}
                className={classes.svg}
                onMouseOver={handleMouseOver}
                role="img"
                aria-label={`Схема зала: ${layout.name}`}
              >
                <SeatLayer layout={layout} />
              </svg>
            </TransformComponent>
          </>
        )}
      </TransformWrapper>

      {hovered && (
        <div className={classes.tooltip} style={{ left: hovered.left, top: hovered.top }}>
          <div>
            <b>{sectionsById.get(hovered.seat.section_id)?.name}</b>
          </div>
          <div>
            Ряд {hovered.seat.row}, место {hovered.seat.number}
          </div>
          <div>
            {categoriesById.get(hovered.seat.category_id)?.name}
            {hoveredPrice != null && ` · ${formatPrice(hoveredPrice)}`}
          </div>
        </div>
      )}
    </div>
  )
}

import { ActionIcon, Group } from '@mantine/core'
import { IconFocusCentered, IconMinus, IconPlus } from '@tabler/icons-react'
import { memo, useCallback, useMemo, useRef, useState } from 'react'
import type { MouseEvent, PointerEvent } from 'react'
import { TransformComponent, TransformWrapper } from 'react-zoom-pan-pinch'

import type {
  HallConfig,
  RinkOut,
  SeatOut,
  SectionOut,
  VenueLayout,
} from '../../api/generated/model'
import { formatPrice } from '../../shared/format'
import type { SeatStatus } from '../booking/useBooking'
import classes from './SeatMap.module.css'

const SEAT_RADIUS = 5.5

export interface SeatMapProps {
  layout: VenueLayout
  /** Режим зала мероприятия: какие секторы показывать и что нарисовать в центре. */
  hallConfig: HallConfig
  /** Цены мероприятия: id категории → копейки. Без них подсказка показывает только место. */
  prices?: Map<number, number>
  /** Занятость зала; без неё схема статична (продажи не идут). */
  status?: SeatStatus
  onSeatClick?: (seat: SeatOut) => void
  onZoneClick?: (section: SectionOut) => void
}

type SeatState = 'free' | 'mine' | 'taken'

function seatState(status: SeatStatus | undefined, seatId: number): SeatState {
  if (!status) return 'free'
  if (status.mine.has(seatId)) return 'mine'
  if (status.held.has(seatId) || status.sold.has(seatId)) return 'taken'
  return 'free'
}

type Hovered =
  | { type: 'seat'; seat: SeatOut; left: number; top: number }
  | { type: 'zone'; section: SectionOut; left: number; top: number }

/** Хоккейная разметка в пропорциях площадки 60×30 м (как у КХЛ/НХЛ). */
function IceRink({ rink }: { rink: RinkOut }) {
  const { x, y, width: w, height: h, radius } = rink
  const cx = x + w / 2
  const cy = y + h / 2
  const goal = w * 0.055 // линия ворот от борта
  const blue = w * 0.125 // синие линии от центра
  const circle = h * 0.176 // радиус кругов вбрасывания
  const dots = [x + goal + w * 0.1, x + w - goal - w * 0.1].flatMap((fx) =>
    [cy - h * 0.26, cy + h * 0.26].map((fy) => [fx, fy] as const),
  )
  return (
    <g>
      <rect x={x} y={y} width={w} height={h} rx={radius} className={classes.ice} />
      <line x1={x + goal} y1={y + 12} x2={x + goal} y2={y + h - 12} className={classes.redLine} />
      <line
        x1={x + w - goal}
        y1={y + 12}
        x2={x + w - goal}
        y2={y + h - 12}
        className={classes.redLine}
      />
      <line x1={cx - blue} y1={y} x2={cx - blue} y2={y + h} className={classes.blueLine} />
      <line x1={cx + blue} y1={y} x2={cx + blue} y2={y + h} className={classes.blueLine} />
      <line x1={cx} y1={y} x2={cx} y2={y + h} className={classes.centerLine} />
      <circle cx={cx} cy={cy} r={circle} className={classes.blueCircle} />
      {dots.map(([fx, fy]) => (
        <g key={`${fx}-${fy}`}>
          <circle cx={fx} cy={fy} r={circle} className={classes.faceoffCircle} />
          <circle cx={fx} cy={fy} r={3} className={classes.faceoffDot} />
        </g>
      ))}
      <path
        d={`M ${x + goal} ${cy - 14} a 14 14 0 0 1 0 28 z`}
        className={classes.crease}
      />
      <path
        d={`M ${x + w - goal} ${cy - 14} a 14 14 0 0 0 0 28 z`}
        className={classes.crease}
      />
    </g>
  )
}

function zoneHint(status: SeatStatus | undefined, section: SectionOut): string {
  const available = status?.zones.get(section.id)
  if (available === undefined) return 'стоячие места'
  return available > 0 ? `свободно ${available} из ${section.capacity}` : 'мест нет'
}

/**
 * Статичная часть схемы: поле, секторы, места. Мемоизирована целиком — при наведении
 * курсора и прочих перерисовках родителя тысячи элементов SVG не пересоздаются.
 */
const SeatLayer = memo(function SeatLayer({
  layout,
  hallConfig,
  status,
  interactive,
}: {
  layout: VenueLayout
  hallConfig: HallConfig
  status?: SeatStatus
  interactive: boolean
}) {
  const colors = useMemo(
    () => new Map(layout.categories.map((c) => [c.id, c.color])),
    [layout.categories],
  )
  const sections = layout.sections.filter((s) => s.configs.includes(hallConfig))
  const visible = new Set(sections.map((s) => s.id))
  const seats = layout.seats.filter((seat) => visible.has(seat.section_id))
  const { rink } = layout

  return (
    <>
      {hallConfig === 'hockey' ? (
        <IceRink rink={rink} />
      ) : (
        <>
          <rect
            x={rink.x}
            y={rink.y}
            width={rink.width}
            height={rink.height}
            rx={rink.radius}
            className={classes.floor}
          />
          <path d={layout.stage_path} className={classes.stage} />
          <text
            x={rink.x - 55}
            y={rink.y + rink.height / 2}
            className={classes.stageLabel}
            transform={`rotate(-90 ${rink.x - 55} ${rink.y + rink.height / 2})`}
          >
            СЦЕНА
          </text>
        </>
      )}

      {sections.map((section) =>
        section.kind === 'standing' ? (
          <g key={section.id}>
            <path
              d={section.path}
              data-section-id={section.id}
              fill={colors.get(section.category_id ?? 0)}
              className={classes.zone}
              data-sold-out={status?.zones.get(section.id) === 0 || undefined}
            />
            <text x={section.label_x} y={section.label_y - 8} className={classes.zoneLabel}>
              {section.name}
            </text>
            <text x={section.label_x} y={section.label_y + 16} className={classes.zoneHint}>
              {zoneHint(status, section)}
            </text>
          </g>
        ) : (
          <g key={section.id}>
            <path d={section.path} className={classes.section} />
            <text x={section.label_x} y={section.label_y} className={classes.sectionLabel}>
              {section.code}
            </text>
          </g>
        ),
      )}

      <g>
        {seats.map((seat) => {
          const state = seatState(status, seat.id)
          return (
            <circle
              key={seat.id}
              data-seat-id={seat.id}
              data-state={state}
              data-interactive={interactive || undefined}
              cx={seat.x}
              cy={seat.y}
              r={state === 'mine' ? SEAT_RADIUS + 1 : SEAT_RADIUS}
              fill={state === 'taken' ? undefined : colors.get(seat.category_id)}
              className={classes.seat}
            />
          )
        })}
      </g>
    </>
  )
})

export function SeatMap({
  layout,
  hallConfig,
  prices,
  status,
  onSeatClick,
  onZoneClick,
}: SeatMapProps) {
  const wrapperRef = useRef<HTMLDivElement>(null)
  const pointerDown = useRef<{ x: number; y: number } | null>(null)
  const [hovered, setHovered] = useState<Hovered | null>(null)
  const interactive = Boolean(onSeatClick)

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
      const wrapper = wrapperRef.current
      const seatId = target.getAttribute('data-seat-id')
      const zoneId = target.getAttribute('data-section-id')
      const seat = seatId ? seatsById.get(Number(seatId)) : undefined
      const zone = zoneId ? sectionsById.get(Number(zoneId)) : undefined
      if (!wrapper || (!seat && !zone)) {
        setHovered(null)
        return
      }
      const box = wrapper.getBoundingClientRect()
      if (seat) {
        const seatBox = target.getBoundingClientRect()
        setHovered({
          type: 'seat',
          seat,
          left: seatBox.left + seatBox.width / 2 - box.left,
          top: seatBox.top - box.top,
        })
      } else if (zone) {
        setHovered({
          type: 'zone',
          section: zone,
          left: e.clientX - box.left,
          top: e.clientY - box.top,
        })
      }
    },
    [seatsById, sectionsById],
  )

  // Клик отличаем от перетаскивания схемы: смещение больше 6 px — это панорамирование.
  const handlePointerDown = (e: PointerEvent) => {
    pointerDown.current = { x: e.clientX, y: e.clientY }
  }
  const handleClick = (e: MouseEvent<SVGSVGElement>) => {
    const start = pointerDown.current
    if (start && Math.hypot(e.clientX - start.x, e.clientY - start.y) > 6) return
    const target = e.target as Element
    const seatId = target.getAttribute('data-seat-id')
    const zoneId = target.getAttribute('data-section-id')
    if (seatId && onSeatClick) {
      const seat = seatsById.get(Number(seatId))
      if (seat && seatState(status, seat.id) !== 'taken') onSeatClick(seat)
    } else if (zoneId && onZoneClick) {
      const zone = sectionsById.get(Number(zoneId))
      if (zone) onZoneClick(zone)
    }
  }

  const hoveredState = hovered?.type === 'seat' ? seatState(status, hovered.seat.id) : undefined
  const categoryId =
    hovered?.type === 'seat' ? hovered.seat.category_id : hovered?.section.category_id
  const hoveredPrice = categoryId != null ? prices?.get(categoryId) : undefined
  const categoryName = categoryId != null ? categoriesById.get(categoryId)?.name : undefined

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
                onPointerDown={handlePointerDown}
                onClick={handleClick}
                role="img"
                aria-label={`Схема зала: ${layout.name}`}
              >
                <SeatLayer
                  layout={layout}
                  hallConfig={hallConfig}
                  status={status}
                  interactive={interactive}
                />
              </svg>
            </TransformComponent>
          </>
        )}
      </TransformWrapper>

      {hovered && (
        <div className={classes.tooltip} style={{ left: hovered.left, top: hovered.top }}>
          {hovered.type === 'seat' ? (
            <>
              <div>
                <b>{sectionsById.get(hovered.seat.section_id)?.name}</b>
              </div>
              <div>
                Ряд {hovered.seat.row}, место {hovered.seat.number}
              </div>
            </>
          ) : (
            <>
              <div>
                <b>{hovered.section.name}</b>
              </div>
              <div>
                Стоячие места ·{' '}
                {status?.zones.has(hovered.section.id)
                  ? `свободно ${status.zones.get(hovered.section.id)}`
                  : `вместимость ${hovered.section.capacity}`}
              </div>
            </>
          )}
          {hoveredState === 'taken' && <div className={classes.tooltipMuted}>Занято</div>}
          {hoveredState === 'mine' && <div className={classes.tooltipMine}>Ваше место</div>}
          <div>
            {categoryName}
            {hoveredPrice != null && ` · ${formatPrice(hoveredPrice)}`}
          </div>
        </div>
      )}
    </div>
  )
}

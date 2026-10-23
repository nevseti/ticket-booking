import { Badge, Text } from '@mantine/core'
import { Link } from 'react-router'

import type { EventCard as EventCardData } from '../../api/generated/model'
import { formatPrice, formatShortDateTime, SALE_STATUS, VENUE_NAME } from '../../shared/format'
import classes from './EventCard.module.css'
import { EventPoster } from './EventPoster'

/** Карточка в духе «Яндекс Афиши»: чистая обложка с ценой, ниже — название и «дата · площадка». */
export function EventCard({ event }: { event: EventCardData }) {
  const status = SALE_STATUS[event.sale_status]

  return (
    <Link to={`/events/${event.id}`} className={classes.card} aria-label={event.title}>
      <div className={classes.cover}>
        <EventPoster
          kind={event.kind}
          title={event.title}
          posterUrl={event.poster_url}
          height={230}
          seed={event.id}
        />
        {event.sale_status !== 'on_sale' && (
          <Badge className={classes.status} variant="filled" color={status.color}>
            {event.sale_status === 'not_started'
              ? `с ${formatShortDateTime(event.sales_start_at)}`
              : status.label}
          </Badge>
        )}
        {event.min_price_kopecks != null && (
          <span className={classes.price}>от {formatPrice(event.min_price_kopecks)}</span>
        )}
      </div>
      <Text className={classes.title} lineClamp={2}>
        {event.title}
      </Text>
      <Text size="sm" c="dimmed" lineClamp={1}>
        {formatShortDateTime(event.starts_at)} · {VENUE_NAME}
      </Text>
    </Link>
  )
}

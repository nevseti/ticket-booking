/**
 * Обложки рисуются в кадре 400×240, но важное (эмблемы, микрофон, облачка) лежит в центральной
 * области 40…360 — она и есть viewBox. Масштаб «meet» показывает её целиком на любой карточке,
 * а поля вокруг заполняет фон, нарисованный с запасом (BLEED) за пределами viewBox.
 * В баннере страницы мероприятия рисунок прижат вправо: слева на фоне идёт заголовок.
 */
export type CoverFit = 'card' | 'banner'

export const COVER_VIEWBOX = '40 0 320 240'

export const COVER_ASPECT: Record<CoverFit, string> = {
  card: 'xMidYMid meet',
  banner: 'xMaxYMid meet',
}

export const BLEED = { x: -600, y: -300, width: 1600, height: 840 }

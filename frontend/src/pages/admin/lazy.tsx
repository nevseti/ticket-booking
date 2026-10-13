import { lazy } from 'react'

// Админка нужна единицам пользователей — грузится отдельным чанком по требованию.
export const AdminEventsPage = lazy(() =>
  import('./AdminEventsPage').then((m) => ({ default: m.AdminEventsPage })),
)
export const AdminEventFormPage = lazy(() =>
  import('./AdminEventFormPage').then((m) => ({ default: m.AdminEventFormPage })),
)

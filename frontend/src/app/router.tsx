import { Center, Loader } from '@mantine/core'
import { Suspense } from 'react'
import type { ReactNode } from 'react'
import { createBrowserRouter } from 'react-router'

import { RequireAdmin, RequireAuth } from '../features/auth/guards'
import { AppLayout } from '../layouts/AppLayout'
import { AdminEventFormPage, AdminEventsPage } from '../pages/admin/lazy'
import { EventPage } from '../pages/EventPage'
import { HomePage } from '../pages/HomePage'
import { LoginPage } from '../pages/LoginPage'
import { NotFoundPage } from '../pages/NotFoundPage'
import { ProfilePage } from '../pages/ProfilePage'
import { RegisterPage } from '../pages/RegisterPage'

const fallback = (
  <Center py={80}>
    <Loader />
  </Center>
)

const auth = (page: ReactNode) => <RequireAuth>{page}</RequireAuth>
const admin = (page: ReactNode) => (
  <RequireAdmin>
    <Suspense fallback={fallback}>{page}</Suspense>
  </RequireAdmin>
)

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: 'events/:eventId', element: <EventPage /> },
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
      { path: 'profile', element: auth(<ProfilePage />) },
      { path: 'admin/events', element: admin(<AdminEventsPage />) },
      { path: 'admin/events/new', element: admin(<AdminEventFormPage />) },
      { path: 'admin/events/:eventId', element: admin(<AdminEventFormPage />) },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])

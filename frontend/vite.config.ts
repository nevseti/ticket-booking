import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// В разработке фронтенд и API работают на одном origin через прокси Vite —
// так же, как на проде через nginx. Поэтому cookie авторизации и SSE не требуют CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    // Явно IPv4: на Windows `localhost` у Vite иначе слушает только [::1].
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY ?? 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
})

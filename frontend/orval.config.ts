import { defineConfig } from 'orval'

// Источник — openapi.json, выгруженный из бэкенда (backend/scripts/export_openapi.py).
// Результат — типы и хуки TanStack Query в src/api/generated (руками не править).
export default defineConfig({
  tickets: {
    input: { target: './openapi.json' },
    output: {
      mode: 'tags-split',
      target: './src/api/generated',
      schemas: './src/api/generated/model',
      client: 'react-query',
      httpClient: 'fetch',
      clean: true,
      override: {
        mutator: { path: './src/api/http.ts', name: 'customFetch' },
        fetch: { includeHttpResponseReturnType: false },
        query: { signal: true },
      },
    },
  },
})

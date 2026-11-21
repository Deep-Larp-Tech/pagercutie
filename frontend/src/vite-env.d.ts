/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `'1'` serves the generated MSW handlers instead of the backend (`pnpm dev:mock`). */
  readonly VITE_MOCK?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

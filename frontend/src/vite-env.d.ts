/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_API_URL: string
  readonly VITE_APP_GOOGLE_CLIENT_ID: string
  readonly VITE_APP_ENCRYPTION_KEY: string
  readonly VITE_APP_EMAILS_API_KEY: string
  readonly VITE_APP_FORCE_TOKEN_TTL_SECONDS: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
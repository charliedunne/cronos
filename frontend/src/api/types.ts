/** Shared TypeScript types mirroring the backend API payloads. */

/** Public representation of a user (mirrors the backend ``UserOut``). */
export interface User {
  id: number
  username: string
  is_admin: boolean
}

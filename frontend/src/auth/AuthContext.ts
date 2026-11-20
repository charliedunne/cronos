/** Auth context object and accessor hook (kept separate from the provider
 * component so the provider file stays fast-refresh friendly). */

import { createContext, useContext } from 'react'
import type { User } from '../api/types'

export interface AuthContextValue {
  /** The authenticated user, or null when no valid session exists. */
  user: User | null
  /** True while the initial ``/auth/me`` check is still in flight. */
  initializing: boolean
  /** Submit credentials; resolves with the user on success. */
  login: (username: string, password: string) => Promise<void>
  /** Revoke the session server-side and clear local state. */
  logout: () => Promise<void>
}

/** Context carrying the session state; null outside an AuthProvider. */
export const AuthContext = createContext<AuthContextValue | null>(null)

/**
 * Access the session state.
 *
 * @return The current auth context value.
 * @throws Error when used outside an AuthProvider.
 */
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (ctx === null) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return ctx
}

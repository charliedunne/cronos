/** Session state for the app: who is logged in, plus login/logout actions.
 *
 * The session itself lives server-side in an httpOnly cookie; this provider
 * only mirrors the authenticated user's profile on the client by checking
 * ``/auth/me`` on first load and after login/logout.
 */

import { useMemo, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import type { User } from '../api/types'
import { AuthContext, type AuthContextValue } from './AuthContext'

/**
 * Provide session state to the component tree.
 *
 * @param children Components rendered inside the provider.
 * @return The provider element.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  // Resolve the session on first load; a 401 simply means "not logged in"
  // and must not be retried.
  const meQuery = useQuery({
    queryKey: ['auth', 'me'],
    queryFn: api.me,
    retry: (_count, error) =>
      !(error instanceof ApiError && error.status === 401),
  })

  const loginMutation = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      api.login(username, password),
    onSuccess: (user) => {
      queryClient.setQueryData(['auth', 'me'], user)
    },
  })

  const logoutMutation = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.setQueryData<User | null>(['auth', 'me'], null)
    },
  })

  const value = useMemo<AuthContextValue>(
    () => ({
      user: meQuery.data ?? null,
      initializing: meQuery.isPending,
      // The resolved user is stored in the query cache; callers only need
      // success/failure, hence the awaited-and-discarded result.
      login: async (username, password) => {
        await loginMutation.mutateAsync({ username, password })
      },
      logout: async () => {
        await logoutMutation.mutateAsync()
      },
    }),
    [meQuery.data, meQuery.isPending, loginMutation, logoutMutation],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

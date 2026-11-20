/** Admin-only user management: list accounts, create, disable, re-enable. */

import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import AppHeader from '../components/AppHeader'
import { api, ApiError } from '../api/client'

/**
 * Human-readable message for an operation failure.
 *
 * @param err The thrown error (usually an :class:`ApiError`).
 * @return The API detail when available, otherwise a generic message.
 */
function messageOf(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Unable to reach the server'
}

/**
 * Render the user management page for administrators.
 *
 * Lists every account with its role and active state, offers a form to
 * create new (non-admin) accounts, and per-row disable/re-enable actions.
 * The list is cached by TanStack Query; each mutation invalidates the
 * ``users`` query so the UI always reflects the latest server state.
 * Failures (duplicate username, unknown user) surface in an error banner.
 *
 * @return The users page element.
 */
export default function UsersPage() {
  const queryClient = useQueryClient()

  const [error, setError] = useState<string | null>(null)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')

  const usersQuery = useQuery({
    queryKey: ['users'],
    queryFn: api.listUsers,
  })
  const users = usersQuery.data ?? []

  /** Drop the cache so the list refetches after a successful mutation. */
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['users'] })
  }

  const createMutation = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      api.createUser(username, password),
    onSuccess: () => {
      setNewUsername('')
      setNewPassword('')
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const disableMutation = useMutation({
    mutationFn: (id: number) => api.disableUser(id),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const enableMutation = useMutation({
    mutationFn: (id: number) => api.enableUser(id),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  /**
   * Submit the create form.
   *
   * @param event The form submit event (prevented to skip page reload).
   */
  function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (!newUsername.trim() || !newPassword) return
    createMutation.mutate({ username: newUsername.trim(), password: newPassword })
  }

  return (
    <div className="app-shell">
      <AppHeader back={{ label: '← Modules', to: '/' }} />
      <main className="content">
        <section className="module-list">
          <h2>Users</h2>

          {error !== null && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <form className="module-create" onSubmit={handleCreate}>
            <input
              type="text"
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="New username"
              aria-label="New username"
              required
            />
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Initial password"
              aria-label="Initial password"
              required
            />
            <button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating…' : 'Create'}
            </button>
          </form>

          {usersQuery.isPending ? (
            <p className="muted">Loading…</p>
          ) : users.length === 0 ? (
            <p className="muted">No users yet. Create the first one above.</p>
          ) : (
            <table className="item-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="item-id">{user.username}</td>
                    <td>{user.is_admin ? 'Admin' : 'User'}</td>
                    <td>{user.is_active ? 'Active' : 'Disabled'}</td>
                    <td>
                      {user.is_active ? (
                        <button
                          type="button"
                          className="danger"
                          disabled={disableMutation.isPending}
                          onClick={() => disableMutation.mutate(user.id)}
                        >
                          Disable
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="secondary"
                          disabled={enableMutation.isPending}
                          onClick={() => enableMutation.mutate(user.id)}
                        >
                          Enable
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </main>
    </div>
  )
}

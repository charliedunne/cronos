/** Module list with create, rename, and delete actions. */

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
 * Render every module with per-row rename/delete actions and a create form.
 *
 * The list is cached by TanStack Query; each mutation invalidates the
 * ``modules`` query so the UI always reflects the latest server state.
 * Failures (duplicate name, non-empty module) surface in an error banner
 * without changing the list.
 *
 * @return The module list element.
 */
export default function ModuleList() {
  const queryClient = useQueryClient()

  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draftName, setDraftName] = useState('')

  const modulesQuery = useQuery({
    queryKey: ['modules'],
    queryFn: api.listModules,
  })
  const modules = modulesQuery.data ?? []

  /** Drop the cache so the list refetches after a successful mutation. */
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['modules'] })
  }

  const createMutation = useMutation({
    mutationFn: (name: string) => api.createModule(name),
    onSuccess: () => {
      setNewName('')
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      api.renameModule(id, name),
    onSuccess: () => {
      setEditingId(null)
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteModule(id),
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
    if (!newName.trim()) return
    createMutation.mutate(newName.trim())
  }

  /** Start inline renaming of a module row. */
  function startRename(id: number, name: string) {
    setEditingId(id)
    setDraftName(name)
    setError(null)
  }

  /**
   * Submit the inline rename form for one row.
   *
   * @param event The form submit event (prevented to skip page reload).
   * @param id The module being renamed.
   */
  function handleRename(event: FormEvent, id: number) {
    event.preventDefault()
    if (!draftName.trim()) return
    renameMutation.mutate({ id, name: draftName.trim() })
  }

  return (
    <section className="module-list">
      <h2>Modules</h2>

      {error !== null && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <form className="module-create" onSubmit={handleCreate}>
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New module name"
          aria-label="New module name"
          required
        />
        <button type="submit" disabled={createMutation.isPending}>
          {createMutation.isPending ? 'Creating…' : 'Create'}
        </button>
      </form>

      {modulesQuery.isPending ? (
        <p className="muted">Loading…</p>
      ) : modules.length === 0 ? (
        <p className="muted">No modules yet. Create the first one above.</p>
      ) : (
        <ul className="module-rows">
          {modules.map((module) =>
            editingId === module.id ? (
              <li key={module.id} className="module-row">
                <form onSubmit={(e) => handleRename(e, module.id)}>
                  <input
                    type="text"
                    value={draftName}
                    onChange={(e) => setDraftName(e.target.value)}
                    aria-label={`New name for ${module.name}`}
                    autoFocus
                    required
                  />
                  <button
                    type="submit"
                    className="secondary"
                    disabled={renameMutation.isPending}
                  >
                    Save
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setEditingId(null)}
                  >
                    Cancel
                  </button>
                </form>
              </li>
            ) : (
              <li key={module.id} className="module-row">
                <Link to={`/modules/${module.id}`} className="module-name">
                  {module.name}
                </Link>
                <span className="spacer" />
                <button
                  type="button"
                  className="secondary"
                  onClick={() => startRename(module.id, module.name)}
                >
                  Rename
                </button>
                <button
                  type="button"
                  className="danger"
                  disabled={deleteMutation.isPending}
                  onClick={() => deleteMutation.mutate(module.id)}
                >
                  Delete
                </button>
              </li>
            ),
          )}
        </ul>
      )}
    </section>
  )
}

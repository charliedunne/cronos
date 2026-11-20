/** Module detail page: requirement list plus create form. */

import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import {
  REQUIREMENT_PRIORITIES,
  REQUIREMENT_STATUSES,
  type RequirementCreate,
  type RequirementPriority,
  type RequirementStatus,
} from '../api/types'
import AppHeader from '../components/AppHeader'

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
 * Render one module's requirements with a create form.
 *
 * The list is cached by TanStack Query under ``requirements/<moduleId>``; a
 * successful create invalidates it so the new requirement (with its system-
 * assigned identifier and defaults) appears immediately. Attribute values
 * chosen in the form persist because the list always reflects server state.
 *
 * @return The module detail page element.
 */
export default function ModuleDetailPage() {
  const { id } = useParams<{ id: string }>()
  const moduleId = Number(id)

  const queryClient = useQueryClient()

  // Create form state; status/priority start at the server defaults so a
  // plain title+text submission produces a "draft"/"medium" requirement.
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [statusValue, setStatusValue] = useState<RequirementStatus>('draft')
  const [priorityValue, setPriorityValue] = useState<RequirementPriority>('medium')
  const [error, setError] = useState<string | null>(null)

  // The module list is already cached from the home page; reuse it for the
  // header name (the API has no single-module GET endpoint).
  const modulesQuery = useQuery({
    queryKey: ['modules'],
    queryFn: api.listModules,
  })
  const moduleName = modulesQuery.data?.find((m) => m.id === moduleId)?.name

  const requirementsQuery = useQuery({
    queryKey: ['requirements', moduleId],
    queryFn: () => api.listRequirements(moduleId),
    enabled: Number.isInteger(moduleId) && moduleId > 0,
  })
  const requirements = requirementsQuery.data ?? []

  const createMutation = useMutation({
    mutationFn: (payload: RequirementCreate) =>
      api.createRequirement(moduleId, payload),
    onSuccess: () => {
      setTitle('')
      setText('')
      setStatusValue('draft')
      setPriorityValue('medium')
      setError(null)
      void queryClient.invalidateQueries({ queryKey: ['requirements', moduleId] })
    },
    onError: (err) => setError(messageOf(err)),
  })

  /**
   * Submit the create form.
   *
   * @param event The form submit event (prevented to skip page reload).
   */
  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    createMutation.mutate({
      title: title.trim(),
      text,
      status: statusValue,
      priority: priorityValue,
    })
  }

  return (
    <div className="app-shell">
      <AppHeader back={{ label: '← Modules', to: '/' }} />
      <main className="content">
        <h1>{moduleName ?? `Module #${id}`}</h1>

        {error !== null && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}

        <form className="requirement-create" onSubmit={handleSubmit}>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            aria-label="Requirement title"
            required
          />
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Text (what the system shall do)"
            aria-label="Requirement text"
            rows={3}
          />
          <label className="field">
            Status
            <select
              value={statusValue}
              onChange={(e) => setStatusValue(e.target.value as RequirementStatus)}
            >
              {REQUIREMENT_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Priority
            <select
              value={priorityValue}
              onChange={(e) => setPriorityValue(e.target.value as RequirementPriority)}
            >
              {REQUIREMENT_PRIORITIES.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={createMutation.isPending}>
            {createMutation.isPending ? 'Creating…' : 'Create requirement'}
          </button>
        </form>

        {requirementsQuery.isPending ? (
          <p className="muted">Loading…</p>
        ) : requirements.length === 0 ? (
          <p className="muted">No requirements yet. Create the first one above.</p>
        ) : (
          <table className="req-table">
            <thead>
              <tr>
                <th>Identifier</th>
                <th>Title</th>
                <th>Text</th>
                <th>Status</th>
                <th>Priority</th>
              </tr>
            </thead>
            <tbody>
              {requirements.map((req) => (
                <tr key={req.id}>
                  <td className="req-id">{req.identifier}</td>
                  <td>{req.title}</td>
                  <td className="req-text">{req.text}</td>
                  <td>{req.status}</td>
                  <td>{req.priority}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <p className="muted">
          <Link to="/">Back to modules</Link>
        </p>
      </main>
    </div>
  )
}

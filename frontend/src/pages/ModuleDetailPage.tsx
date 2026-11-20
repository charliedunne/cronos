/** Module detail page: requirement list, create form, and lock-based editing. */

import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import {
  REQUIREMENT_PRIORITIES,
  REQUIREMENT_STATUSES,
  type Requirement,
  type RequirementCreate,
  type RequirementPriority,
  type RequirementStatus,
  type RequirementUpdate,
} from '../api/types'
import { useAuth } from '../auth/AuthContext'
import AppHeader from '../components/AppHeader'

/** Editable attribute draft for the single inline-edit row. */
interface EditDraft {
  title: string
  text: string
  status: RequirementStatus
  priority: RequirementPriority
}

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
 * Render one module's requirements with a create form and lock-based editing.
 *
 * The list is cached by TanStack Query under ``requirements/<moduleId>`` and
 * invalidated after every mutation so lock state always reflects the server.
 * Editing follows the editing-locks spec: a user first blocks (locks) a
 * requirement, edits it while holding the lock, then unblocks; non-holders
 * see the holder badge but cannot edit. Only one row is editable at a time.
 *
 * @return The module detail page element.
 */
export default function ModuleDetailPage() {
  const { user } = useAuth()
  const { id } = useParams<{ id: string }>()
  const moduleId = Number(id)

  const queryClient = useQueryClient()

  // Create form state; status/priority start at the server defaults so a
  // plain title+text submission produces a "draft"/"medium" requirement.
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [statusValue, setStatusValue] = useState<RequirementStatus>('draft')
  const [priorityValue, setPriorityValue] = useState<RequirementPriority>('medium')

  // Inline editing: at most one row is editable at a time; the draft holds
  // that row's attribute values until saved or cancelled.
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState<EditDraft>({
    title: '',
    text: '',
    status: 'draft',
    priority: 'medium',
  })

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

  /** Re-fetch the requirement list so lock state and attributes refresh. */
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['requirements', moduleId] })
  }

  const createMutation = useMutation({
    mutationFn: (payload: RequirementCreate) =>
      api.createRequirement(moduleId, payload),
    onSuccess: () => {
      setTitle('')
      setText('')
      setStatusValue('draft')
      setPriorityValue('medium')
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const lockMutation = useMutation({
    mutationFn: (reqId: number) => api.lockRequirement(reqId),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const unlockMutation = useMutation({
    mutationFn: (reqId: number) => api.unlockRequirement(reqId),
    onSuccess: () => {
      setEditingId(null)
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  // Administrators may force-release a lock held by anyone else; the
  // holder's own Unblock already covers their own locks.
  const forceReleaseMutation = useMutation({
    mutationFn: (reqId: number) => api.forceReleaseRequirement(reqId),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ reqId, payload }: { reqId: number; payload: RequirementUpdate }) =>
      api.updateRequirement(reqId, payload),
    onSuccess: () => {
      setEditingId(null)
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

  /**
   * Switch a row into inline edit mode, seeding the draft from its values.
   *
   * @param req The requirement to edit (the caller must hold its lock).
   */
  function startEdit(req: Requirement) {
    setEditingId(req.id)
    setDraft({ title: req.title, text: req.text, status: req.status, priority: req.priority })
  }

  /** Leave inline edit mode without saving. */
  function cancelEdit() {
    setEditingId(null)
  }

  /**
   * Save the draft for the row currently in edit mode.
   *
   * @param reqId The requirement being edited (the caller holds its lock).
   */
  function saveEdit(reqId: number) {
    if (!draft.title.trim()) return
    updateMutation.mutate({
      reqId,
      payload: {
        title: draft.title.trim(),
        text: draft.text,
        status: draft.status,
        priority: draft.priority,
      },
    })
  }

  if (!user) {
    // The route guard normally prevents this; render nothing defensively.
    return null
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
                <th>Lock</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {requirements.map((req) => (
                <RequirementRow
                  key={req.id}
                  req={req}
                  isHolder={req.locked_by !== null && req.locked_by === user.username}
                  isEditing={editingId === req.id}
                  draft={draft}
                  onDraftChange={setDraft}
                  onStartEdit={() => startEdit(req)}
                  onCancelEdit={cancelEdit}
                  onSaveEdit={() => saveEdit(req.id)}
                  onBlock={() => lockMutation.mutate(req.id)}
                  onUnblock={() => unlockMutation.mutate(req.id)}
                  canForceUnblock={
                    user.is_admin && req.locked_by !== null && req.locked_by !== user.username
                  }
                  onForceUnblock={() => forceReleaseMutation.mutate(req.id)}
                  busy={
                    lockMutation.isPending ||
                    unlockMutation.isPending ||
                    forceReleaseMutation.isPending ||
                    updateMutation.isPending
                  }
                />
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

interface RequirementRowProps {
  /** The requirement to render. */
  req: Requirement
  /** True when the signed-in user holds the lock on this requirement. */
  isHolder: boolean
  /** True while this row is in inline edit mode. */
  isEditing: boolean
  /** Draft attribute values of the row currently being edited. */
  draft: EditDraft
  /** Update the shared edit draft (only meaningful for the editing row). */
  onDraftChange: (draft: EditDraft) => void
  /** Enter inline edit mode for this row. */
  onStartEdit: () => void
  /** Leave inline edit mode without saving. */
  onCancelEdit: () => void
  /** Save the draft as a PATCH to this requirement. */
  onSaveEdit: () => void
  /** Acquire the lock on this requirement. */
  onBlock: () => void
  /** Release the lock on this requirement (holder only). */
  onUnblock: () => void
  /** True when the viewer may force-release a lock held by someone else. */
  canForceUnblock: boolean
  /** Force-release the lock on this requirement (admin only). */
  onForceUnblock: () => void
  /** True while any row mutation is in flight (disables action buttons). */
  busy: boolean
}

/**
 * Render one requirement as a table row.
 *
 * In display mode the row shows the attributes, a lock badge naming the
 * holder when locked, and the actions allowed by the editing-locks spec:
 * anyone may Block an unlocked requirement; only the holder may Edit or
 * Unblock; non-holders see a disabled Edit. Administrators additionally get
 * a Force unblock button on locks held by someone else (the holder's own
 * Unblock covers their own locks). In edit mode (holder only) the attribute
 * cells become inputs bound to the shared draft.
 *
 * @param props Row data and callbacks.
 * @return The table row element.
 */
function RequirementRow({
  req,
  isHolder,
  isEditing,
  draft,
  onDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onBlock,
  onUnblock,
  canForceUnblock,
  onForceUnblock,
  busy,
}: RequirementRowProps) {
  if (isEditing) {
    return (
      <tr className="req-edit-row">
        <td className="req-id">{req.identifier}</td>
        <td>
          <input
            type="text"
            value={draft.title}
            onChange={(e) => onDraftChange({ ...draft, title: e.target.value })}
            aria-label="Edit title"
            required
          />
        </td>
        <td>
          <textarea
            value={draft.text}
            onChange={(e) => onDraftChange({ ...draft, text: e.target.value })}
            rows={2}
            aria-label="Edit text"
          />
        </td>
        <td>
          <select
            value={draft.status}
            onChange={(e) =>
              onDraftChange({ ...draft, status: e.target.value as RequirementStatus })
            }
            aria-label="Edit status"
          >
            {REQUIREMENT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </td>
        <td>
          <select
            value={draft.priority}
            onChange={(e) =>
              onDraftChange({ ...draft, priority: e.target.value as RequirementPriority })
            }
            aria-label="Edit priority"
          >
            {REQUIREMENT_PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </td>
        <td className="lock-cell">
          <span className="lock-badge mine">🔒 you</span>
        </td>
        <td className="row-actions">
          <button type="button" onClick={onSaveEdit} disabled={busy}>
            Save
          </button>
          <button type="button" className="secondary" onClick={onCancelEdit} disabled={busy}>
            Cancel
          </button>
        </td>
      </tr>
    )
  }

  return (
    <tr>
      <td className="req-id">{req.identifier}</td>
      <td>{req.title}</td>
      <td className="req-text">{req.text}</td>
      <td>{req.status}</td>
      <td>{req.priority}</td>
      <td className="lock-cell">
        {req.locked_by !== null ? (
          <span className={isHolder ? 'lock-badge mine' : 'lock-badge'}>
            🔒 {req.locked_by}
          </span>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="row-actions">
        {req.locked_by === null ? (
          <button type="button" onClick={onBlock} disabled={busy}>
            Block
          </button>
        ) : isHolder ? (
          <>
            <button type="button" onClick={onStartEdit} disabled={busy}>
              Edit
            </button>
            <button type="button" className="secondary" onClick={onUnblock} disabled={busy}>
              Unblock
            </button>
          </>
        ) : (
          <>
            <button type="button" disabled title={`Locked by ${req.locked_by}`}>
              Edit
            </button>
            {canForceUnblock && (
              <button
                type="button"
                className="secondary"
                onClick={onForceUnblock}
                disabled={busy}
              >
                Force unblock
              </button>
            )}
          </>
        )}
      </td>
    </tr>
  )
}

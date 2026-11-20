/** Module detail page: work-item list, dynamic create form, lock-based editing. */

import { useEffect, useState, type FormEvent, type ReactElement } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../api/client'
import type { AttributeDefinitionOut, WorkItem, WorkItemType } from '../api/types'
import { useAuth } from '../auth/AuthContext'
import AppHeader from '../components/AppHeader'

/** Raw form values keyed by attribute key (strings for text-like inputs). */
type RawValues = Record<string, string | boolean>

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
 * Convert a stored attribute value to the raw display value of its input.
 *
 * @param def The definition describing the value's data type.
 * @param value The stored value (may be absent).
 * @return A string for text-like inputs, a boolean for checkboxes.
 */
function toRaw(def: AttributeDefinitionOut, value: unknown): string | boolean {
  if (def.data_type === 'boolean') return value === true
  if (value === null || value === undefined) return ''
  return String(value)
}

/**
 * Seed raw form values from a type's attribute defaults.
 *
 * @param type The type whose attributes to seed.
 * @return Raw values for every attribute: the default where declared, else an
 *         empty string (or ``false`` for checkboxes).
 */
function seedDefaults(type: WorkItemType): RawValues {
  const raw: RawValues = {}
  for (const def of type.attributes) {
    if (def.default_value !== null && def.default_value !== undefined) {
      raw[def.key] = toRaw(def, def.default_value)
    } else {
      raw[def.key] = def.data_type === 'boolean' ? false : ''
    }
  }
  return raw
}

/**
 * Build the attribute payload map from raw form values.
 *
 * Empty text-like inputs are omitted so that server-side defaults apply or a
 * required-attribute error surfaces; booleans are always sent. Conformance of
 * the supplied values is reported by the API (422).
 *
 * @param defs The selected type's attribute definitions.
 * @param raw Raw form values keyed by attribute key.
 * @return The attribute values to send in the request body.
 */
function toPayload(defs: AttributeDefinitionOut[], raw: RawValues): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const def of defs) {
    const value = raw[def.key]
    if (def.data_type === 'boolean') {
      out[def.key] = value === true
    } else if (typeof value === 'string' && value !== '') {
      out[def.key] = def.data_type === 'integer' ? Number(value) : value
    }
  }
  return out
}

/**
 * Render a stored attribute value for display in the list.
 *
 * @param value The stored value (may be absent).
 * @return A human-readable rendering ('—' when absent).
 */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return String(value)
}

interface AttributeInputProps {
  /** The attribute definition the input renders. */
  def: AttributeDefinitionOut
  /** Current raw value of the input. */
  value: string | boolean
  /** Report a changed raw value. */
  onChange: (value: string | boolean) => void
}

/**
 * Render a single attribute input matching the definition's data type:
 * text/textarea for string/text, number for integer, checkbox for boolean,
 * date picker for date, and a select over the options for enum.
 *
 * @param props Definition, current value, and change callback.
 * @return The labelled input element.
 */
function AttributeInput({ def, value, onChange }: AttributeInputProps) {
  const label = def.required ? `${def.label} *` : def.label
  const text = typeof value === 'string' ? value : ''

  let control: ReactElement
  switch (def.data_type) {
    case 'text':
      control = (
        <textarea rows={2} value={text} onChange={(e) => onChange(e.target.value)} />
      )
      break
    case 'integer':
      control = (
        <input type="number" step={1} value={text} onChange={(e) => onChange(e.target.value)} />
      )
      break
    case 'boolean':
      control = (
        <input
          type="checkbox"
          checked={value === true}
          onChange={(e) => onChange(e.target.checked)}
        />
      )
      break
    case 'date':
      control = (
        <input type="date" value={text} onChange={(e) => onChange(e.target.value)} />
      )
      break
    case 'enum': {
      const options = def.options ?? []
      control = (
        <select value={text} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {text !== '' && !options.includes(text) && (
            // Keep a stale stored value visible until the user picks a new one.
            <option value={text} disabled>
              {text} (invalid)
            </option>
          )}
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      )
      break
    }
    default:
      control = <input type="text" value={text} onChange={(e) => onChange(e.target.value)} />
  }

  return (
    <label className="field">
      {label}
      {control}
    </label>
  )
}

/**
 * Render one module's work items with a dynamic create form and lock-based
 * editing.
 *
 * The list is cached by TanStack Query under ``work-items/<moduleId>`` and
 * invalidated after every mutation so lock state always reflects the server.
 * The create form offers a type selector (the catalog is fetched from the
 * open type-registry endpoint) and renders one input per attribute of the
 * selected type, prefilled with its defaults. Editing follows the
 * editing-locks spec: a user first blocks (locks) an item, edits it while
 * holding the lock, then unblocks; non-holders see the holder badge but
 * cannot edit. Only one row is editable at a time.
 *
 * @return The module detail page element.
 */
export default function ModuleDetailPage() {
  const { user } = useAuth()
  const { id } = useParams<{ id: string }>()
  const moduleId = Number(id)

  const queryClient = useQueryClient()

  // Create form state; the type defaults to the first catalog entry and the
  // attribute values are seeded from the selected type's defaults.
  const [selectedTypeId, setSelectedTypeId] = useState<number | null>(null)
  const [title, setTitle] = useState('')
  const [createValues, setCreateValues] = useState<RawValues>({})

  // Inline editing: at most one row is editable at a time; the draft holds
  // that row's title and attribute values until saved or cancelled.
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draftTitle, setDraftTitle] = useState('')
  const [draftValues, setDraftValues] = useState<RawValues>({})

  const [error, setError] = useState<string | null>(null)

  // The module list is already cached from the home page; reuse it for the
  // header name (the API has no single-module GET endpoint).
  const modulesQuery = useQuery({
    queryKey: ['modules'],
    queryFn: api.listModules,
  })
  const moduleName = modulesQuery.data?.find((m) => m.id === moduleId)?.name

  const typesQuery = useQuery({
    queryKey: ['work-item-types'],
    queryFn: api.listWorkItemTypes,
  })
  const types = typesQuery.data ?? []

  const itemsQuery = useQuery({
    queryKey: ['work-items', moduleId],
    queryFn: () => api.listWorkItems(moduleId),
    enabled: Number.isInteger(moduleId) && moduleId > 0,
  })
  const items = itemsQuery.data ?? []

  // Default the type selector to the first catalog entry (or recover when the
  // selected type vanished) and seed the form from its attribute defaults.
  useEffect(() => {
    if (types.length === 0) return
    const valid = selectedTypeId !== null && types.some((t) => t.id === selectedTypeId)
    if (!valid) {
      const first = types[0]
      setSelectedTypeId(first.id)
      setCreateValues(seedDefaults(first))
    }
  }, [types, selectedTypeId])

  const activeType = types.find((t) => t.id === selectedTypeId)

  /** Re-fetch the work-item list so lock state and attributes refresh. */
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['work-items', moduleId] })
  }

  /** Switch the create form to another type, reseeding its attribute values. */
  function handleTypeChange(typeId: number) {
    const type = types.find((t) => t.id === typeId)
    if (!type) return
    setSelectedTypeId(typeId)
    setCreateValues(seedDefaults(type))
  }

  const createMutation = useMutation({
    mutationFn: (payload: Parameters<typeof api.createWorkItem>[1]) =>
      api.createWorkItem(moduleId, payload),
    onSuccess: () => {
      setTitle('')
      if (activeType) setCreateValues(seedDefaults(activeType))
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const lockMutation = useMutation({
    mutationFn: (itemId: number) => api.lockWorkItem(itemId),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const unlockMutation = useMutation({
    mutationFn: (itemId: number) => api.unlockWorkItem(itemId),
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
    mutationFn: (itemId: number) => api.forceReleaseWorkItem(itemId),
    onSuccess: () => {
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  const updateMutation = useMutation({
    mutationFn: ({ itemId, payload }: { itemId: number; payload: Parameters<typeof api.updateWorkItem>[1] }) =>
      api.updateWorkItem(itemId, payload),
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
    if (!title.trim() || activeType === undefined) return
    createMutation.mutate({
      type_id: activeType.id,
      title: title.trim(),
      attributes: toPayload(activeType.attributes, createValues),
    })
  }

  /**
   * Switch a row into inline edit mode, seeding the draft from its values.
   *
   * @param item The work item to edit (the caller must hold its lock).
   */
  function startEdit(item: WorkItem) {
    const type = types.find((t) => t.id === item.type.id)
    const raw: RawValues = {}
    for (const def of type?.attributes ?? []) {
      raw[def.key] = toRaw(def, item.attributes[def.key])
    }
    setEditingId(item.id)
    setDraftTitle(item.title)
    setDraftValues(raw)
  }

  /** Leave inline edit mode without saving. */
  function cancelEdit() {
    setEditingId(null)
  }

  /**
   * Save the draft for the row currently in edit mode.
   *
   * @param item The work item being edited (the caller holds its lock).
   */
  function saveEdit(item: WorkItem) {
    if (!draftTitle.trim()) return
    const type = types.find((t) => t.id === item.type.id)
    updateMutation.mutate({
      itemId: item.id,
      payload: {
        title: draftTitle.trim(),
        attributes: toPayload(type?.attributes ?? [], draftValues),
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

        <form className="work-item-create" onSubmit={handleSubmit}>
          <label className="field">
            Type
            <select
              value={selectedTypeId ?? ''}
              onChange={(e) => handleTypeChange(Number(e.target.value))}
              aria-label="Work item type"
              disabled={types.length === 0}
            >
              {types.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.id_prefix})
                </option>
              ))}
            </select>
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            aria-label="Work item title"
            required
          />
          {activeType !== undefined && (
            <div className="attr-grid">
              {activeType.attributes.map((def) => (
                <AttributeInput
                  key={def.key}
                  def={def}
                  value={createValues[def.key] ?? (def.data_type === 'boolean' ? false : '')}
                  onChange={(v) => setCreateValues((prev) => ({ ...prev, [def.key]: v }))}
                />
              ))}
            </div>
          )}
          <button type="submit" disabled={createMutation.isPending || activeType === undefined}>
            {createMutation.isPending ? 'Creating…' : 'Create work item'}
          </button>
        </form>

        {itemsQuery.isPending ? (
          <p className="muted">Loading…</p>
        ) : items.length === 0 ? (
          <p className="muted">No work items yet. Create the first one above.</p>
        ) : (
          <table className="item-table">
            <thead>
              <tr>
                <th>Identifier</th>
                <th>Type</th>
                <th>Title</th>
                <th>Attributes</th>
                <th>Lock</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <WorkItemRow
                  key={item.id}
                  item={item}
                  defs={types.find((t) => t.id === item.type.id)?.attributes ?? []}
                  isHolder={item.locked_by !== null && item.locked_by === user.username}
                  isEditing={editingId === item.id}
                  draftTitle={draftTitle}
                  draftValues={draftValues}
                  onDraftChange={(title, values) => {
                    setDraftTitle(title)
                    setDraftValues(values)
                  }}
                  onStartEdit={() => startEdit(item)}
                  onCancelEdit={cancelEdit}
                  onSaveEdit={() => saveEdit(item)}
                  onBlock={() => lockMutation.mutate(item.id)}
                  onUnblock={() => unlockMutation.mutate(item.id)}
                  canForceUnblock={
                    user.is_admin && item.locked_by !== null && item.locked_by !== user.username
                  }
                  onForceUnblock={() => forceReleaseMutation.mutate(item.id)}
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

interface WorkItemRowProps {
  /** The work item to render. */
  item: WorkItem
  /** Attribute definitions of the item's type (for generic rendering). */
  defs: AttributeDefinitionOut[]
  /** True when the signed-in user holds the lock on this item. */
  isHolder: boolean
  /** True while this row is in inline edit mode. */
  isEditing: boolean
  /** Draft title of the row currently being edited. */
  draftTitle: string
  /** Draft attribute values of the row currently being edited. */
  draftValues: RawValues
  /** Update the shared edit draft (only meaningful for the editing row). */
  onDraftChange: (title: string, values: RawValues) => void
  /** Enter inline edit mode for this row. */
  onStartEdit: () => void
  /** Leave inline edit mode without saving. */
  onCancelEdit: () => void
  /** Save the draft as a PATCH to this work item. */
  onSaveEdit: () => void
  /** Acquire the lock on this work item. */
  onBlock: () => void
  /** Release the lock on this work item (holder only). */
  onUnblock: () => void
  /** True when the viewer may force-release a lock held by someone else. */
  canForceUnblock: boolean
  /** Force-release the lock on this work item (admin only). */
  onForceUnblock: () => void
  /** True while any row mutation is in flight (disables action buttons). */
  busy: boolean
}

/**
 * Render one work item as a table row.
 *
 * In display mode the row shows a type badge, the title, every attribute of
 * the item's type rendered generically (label plus value), a lock badge
 * naming the holder when locked, and the actions allowed by the
 * editing-locks spec: anyone may Block an unlocked item; only the holder may
 * Edit or Unblock; non-holders see a disabled Edit. Administrators
 * additionally get a Force unblock button on locks held by someone else. In
 * edit mode (holder only) the title and attribute cells become inputs bound
 * to the shared draft.
 *
 * @param props Row data and callbacks.
 * @return The table row element.
 */
function WorkItemRow({
  item,
  defs,
  isHolder,
  isEditing,
  draftTitle,
  draftValues,
  onDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onBlock,
  onUnblock,
  canForceUnblock,
  onForceUnblock,
  busy,
}: WorkItemRowProps) {
  if (isEditing) {
    return (
      <tr className="item-edit-row">
        <td className="item-id">{item.identifier}</td>
        <td>
          <span className="type-badge">{item.type.name}</span>
        </td>
        <td>
          <input
            type="text"
            value={draftTitle}
            onChange={(e) => onDraftChange(e.target.value, draftValues)}
            aria-label="Edit title"
            required
          />
        </td>
        <td>
          <div className="attr-edit">
            {defs.map((def) => (
              <AttributeInput
                key={def.key}
                def={def}
                value={draftValues[def.key] ?? (def.data_type === 'boolean' ? false : '')}
                onChange={(v) => onDraftChange(draftTitle, { ...draftValues, [def.key]: v })}
              />
            ))}
          </div>
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
      <td className="item-id">{item.identifier}</td>
      <td>
        <span className="type-badge">{item.type.name}</span>
      </td>
      <td>{item.title}</td>
      <td className="item-text">
        {defs.map((def) => (
          <div key={def.key}>
            <span className="muted">{def.label}: </span>
            {formatValue(item.attributes[def.key])}
          </div>
        ))}
      </td>
      <td className="lock-cell">
        {item.locked_by !== null ? (
          <span className={isHolder ? 'lock-badge mine' : 'lock-badge'}>
            🔒 {item.locked_by}
          </span>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="row-actions">
        {item.locked_by === null ? (
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
            <button type="button" disabled title={`Locked by ${item.locked_by}`}>
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

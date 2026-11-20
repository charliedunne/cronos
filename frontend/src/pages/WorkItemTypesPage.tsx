/** Admin-only work item type registry: manage types and attribute definitions. */

import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import AppHeader from '../components/AppHeader'
import { api, ApiError } from '../api/client'
import {
  ATTRIBUTE_DATA_TYPES,
  type AttributeDataType,
  type AttributeDefinition,
  type AttributeDefinitionOut,
  type WorkItemType,
} from '../api/types'

/**
 * Human-readable message for an operation failure.
 *
 * @param err The thrown error (usually an :class:`ApiError`).
 * @return The API detail when available, otherwise a generic message.
 */
function messageOf(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Unable to reach the server'
}

/** Form state for the add/edit attribute form (raw input values). */
interface AttrFormState extends AttrFormFields {
  /** The attribute id being edited, or null when adding a new one. */
  editId: number | null
}

/** Raw field values of the attribute form before payload conversion. */
interface AttrFormFields {
  key: string
  label: string
  data_type: AttributeDataType
  /** Comma-separated enum options (only used for enum attributes). */
  optionsText: string
  required: boolean
  /** Raw default value as typed in the form ('' means no default). */
  defaultRaw: string
  /** Raw position as typed in the form. */
  position: string
}

/** Empty attribute form state used when adding a new definition. */
const EMPTY_ATTR_FORM: AttrFormFields = {
  key: '',
  label: '',
  data_type: 'string',
  optionsText: '',
  required: false,
  defaultRaw: '',
  position: '0',
}

/**
 * Parse a comma-separated options list into trimmed non-empty entries.
 *
 * @param text The raw options input value.
 * @return The parsed option strings.
 */
function parseOptions(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s !== '')
}

/**
 * Build the ``default_value`` payload from the raw form input.
 *
 * @param dataType The attribute's data type.
 * @param raw The raw default input ('' means no default).
 * @return The typed default value, or null when none was given.
 */
function buildDefault(dataType: AttributeDataType, raw: string): unknown {
  if (raw === '') return null
  if (dataType === 'integer') return Number(raw)
  if (dataType === 'boolean') return raw === 'true'
  return raw
}

/** Convert a stored default value to the raw form input for its data type. */
function rawDefault(value: unknown): string {
  if (value === null || value === undefined) return ''
  return String(value)
}

interface DefaultInputProps {
  /** The attribute's data type (drives the input kind). */
  dataType: AttributeDataType
  /** Raw comma-separated enum options (for the enum default select). */
  optionsText: string
  /** Current raw default value. */
  value: string
  /** Report a changed raw default value. */
  onChange: (value: string) => void
}

/**
 * Render the default-value input matching the attribute's data type: text for
 * string/text, number for integer, a three-way select for boolean, a date
 * picker for date, and a select over the declared options for enum. An empty
 * value means "no default".
 *
 * @param props Data type, options, current value, and change callback.
 * @return The input element (labelled by its surrounding form field).
 */
function DefaultInput({ dataType, optionsText, value, onChange }: DefaultInputProps) {
  switch (dataType) {
    case 'integer':
      return (
        <input type="number" step={1} value={value} onChange={(e) => onChange(e.target.value)} />
      )
    case 'boolean':
      return (
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">(none)</option>
          <option value="false">false</option>
          <option value="true">true</option>
        </select>
      )
    case 'date':
      return <input type="date" value={value} onChange={(e) => onChange(e.target.value)} />
    case 'enum':
      return (
        <select value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">(none)</option>
          {parseOptions(optionsText).map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      )
    default:
      return <input type="text" value={value} onChange={(e) => onChange(e.target.value)} />
  }
}

interface TypeSectionProps {
  /** The work-item type to manage. */
  type: WorkItemType
  /** Report a mutation failure to the page-level error banner. */
  reportError: (message: string) => void
}

/**
 * Render one work-item type with its management UI: an edit form for the
 * type's name, id prefix, and description (name and prefix are locked for
 * built-in types), a delete action for non-built-in types, the attribute
 * definition table, and an add/edit form for attributes.
 *
 * @param props The type to render and the error reporter.
 * @return The type section element.
 */
function TypeSection({ type, reportError }: TypeSectionProps) {
  const queryClient = useQueryClient()

  // Type edit form state (hidden until "Edit" is pressed).
  const [editingType, setEditingType] = useState(false)
  const [typeName, setTypeName] = useState(type.name)
  const [typePrefix, setTypePrefix] = useState(type.id_prefix)
  const [typeDescription, setTypeDescription] = useState(type.description)

  // Attribute form state: null when hidden.
  const [attrForm, setAttrForm] = useState<AttrFormState | null>(null)

  /** Drop the cache so the type list refetches after a successful mutation. */
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['work-item-types'] })
  }

  const updateTypeMutation = useMutation({
    mutationFn: () =>
      api.updateWorkItemType(type.id, {
        name: type.is_builtin ? undefined : typeName.trim(),
        id_prefix: type.is_builtin ? undefined : typePrefix.trim(),
        description: typeDescription,
      }),
    onSuccess: () => {
      setEditingType(false)
      invalidate()
    },
    onError: (err) => reportError(messageOf(err)),
  })

  const deleteTypeMutation = useMutation({
    mutationFn: () => api.deleteWorkItemType(type.id),
    onSuccess: () => invalidate(),
    onError: (err) => reportError(messageOf(err)),
  })

  const createAttrMutation = useMutation({
    mutationFn: (payload: AttributeDefinition) => api.createAttribute(type.id, payload),
    onSuccess: () => {
      setAttrForm(null)
      invalidate()
    },
    onError: (err) => reportError(messageOf(err)),
  })

  const updateAttrMutation = useMutation({
    mutationFn: ({ editId, payload }: { editId: number; payload: AttributeDefinition }) =>
      api.updateAttribute(type.id, editId, payload),
    onSuccess: () => {
      setAttrForm(null)
      invalidate()
    },
    onError: (err) => reportError(messageOf(err)),
  })

  const deleteAttrMutation = useMutation({
    mutationFn: (attributeId: number) => api.deleteAttribute(type.id, attributeId),
    onSuccess: () => invalidate(),
    onError: (err) => reportError(messageOf(err)),
  })

  /** Open the type edit form prefilled with the current values. */
  function startTypeEdit() {
    setTypeName(type.name)
    setTypePrefix(type.id_prefix)
    setTypeDescription(type.description)
    setEditingType(true)
  }

  /** Close the type edit form without saving. */
  function cancelTypeEdit() {
    setEditingType(false)
  }

  /**
   * Submit the type edit form.
   *
   * @param event The form submit event (prevented to skip page reload).
   */
  function handleTypeEdit(event: FormEvent) {
    event.preventDefault()
    if (!type.is_builtin && !typeName.trim()) return
    updateTypeMutation.mutate()
  }

  /** Delete the type after confirmation (refused by the API when it has items). */
  function handleDeleteType() {
    if (!window.confirm(`Delete type "${type.name}"? This cannot be undone.`)) return
    deleteTypeMutation.mutate()
  }

  /** Open the attribute form in add mode, suggesting the next free position. */
  function startAddAttribute() {
    // Stored definitions always carry a concrete position (the server
    // auto-assigns on create), so `?? 0` only guards the type.
    const next = type.attributes.reduce((max, a) => Math.max(max, a.position ?? 0), -1) + 1
    setAttrForm({ ...EMPTY_ATTR_FORM, editId: null, position: String(next) })
  }

  /** Open the attribute form in edit mode for one definition. */
  function startEditAttribute(def: AttributeDefinitionOut) {
    setAttrForm({
      editId: def.id,
      key: def.key,
      label: def.label,
      data_type: def.data_type,
      optionsText: (def.options ?? []).join(', '),
      required: def.required,
      defaultRaw: rawDefault(def.default_value),
      position: String(def.position),
    })
  }

  /** Close the attribute form without saving. */
  function cancelAttribute() {
    setAttrForm(null)
  }

  /**
   * Submit the attribute form (add or edit).
   *
   * @param event The form submit event (prevented to skip page reload).
   */
  function handleAttributeSubmit(event: FormEvent) {
    event.preventDefault()
    if (attrForm === null) return
    const key = attrForm.key.trim()
    const label = attrForm.label.trim()
    if (!key || !label) return
    const payload: AttributeDefinition = {
      key,
      label,
      data_type: attrForm.data_type,
      options: attrForm.data_type === 'enum' ? parseOptions(attrForm.optionsText) : null,
      required: attrForm.required,
      default_value: buildDefault(attrForm.data_type, attrForm.defaultRaw),
      // An empty position lets the server auto-assign (append on create,
      // leave unchanged on update).
      position: attrForm.position.trim() === '' ? null : Number(attrForm.position),
    }
    if (attrForm.editId === null) {
      createAttrMutation.mutate(payload)
    } else {
      updateAttrMutation.mutate({ editId: attrForm.editId, payload })
    }
  }

  const busy =
    updateTypeMutation.isPending ||
    deleteTypeMutation.isPending ||
    createAttrMutation.isPending ||
    updateAttrMutation.isPending ||
    deleteAttrMutation.isPending

  return (
    <section className="type-section">
      <div className="type-head">
        <strong>{type.name}</strong>
        <span className="item-id">{type.id_prefix}</span>
        {type.is_builtin && <span className="type-badge builtin">built-in</span>}
        <span className="spacer" />
        {!editingType ? (
          <>
            <button type="button" className="secondary" onClick={startTypeEdit} disabled={busy}>
              Edit
            </button>
            {!type.is_builtin && (
              <button
                type="button"
                className="danger"
                onClick={handleDeleteType}
                disabled={busy}
              >
                Delete
              </button>
            )}
          </>
        ) : (
          <>
            <button type="button" onClick={() => updateTypeMutation.mutate()} disabled={busy}>
              Save
            </button>
            <button type="button" className="secondary" onClick={cancelTypeEdit} disabled={busy}>
              Cancel
            </button>
          </>
        )}
      </div>

      {editingType ? (
        <form className="attr-form-grid" onSubmit={handleTypeEdit}>
          <label className="field">
            Name
            <input
              type="text"
              value={typeName}
              onChange={(e) => setTypeName(e.target.value)}
              disabled={type.is_builtin}
              aria-label="Type name"
            />
          </label>
          <label className="field">
            ID prefix
            <input
              type="text"
              value={typePrefix}
              onChange={(e) => setTypePrefix(e.target.value)}
              disabled={type.is_builtin}
              aria-label="ID prefix"
            />
          </label>
          <label className="field">
            Description
            <input
              type="text"
              value={typeDescription}
              onChange={(e) => setTypeDescription(e.target.value)}
              aria-label="Type description"
            />
          </label>
        </form>
      ) : (
        type.description !== '' && <p className="muted">{type.description}</p>
      )}

      <table className="item-table">
        <thead>
          <tr>
            <th>Key</th>
            <th>Label</th>
            <th>Data type</th>
            <th>Options</th>
            <th>Required</th>
            <th>Default</th>
            <th>Position</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {type.attributes.map((def) => (
            <tr key={def.id}>
              <td className="item-id">{def.key}</td>
              <td>{def.label}</td>
              <td>{def.data_type}</td>
              <td className="muted">{def.options?.join(', ') ?? '—'}</td>
              <td>{def.required ? 'yes' : 'no'}</td>
              <td className="muted">
                {def.default_value === null || def.default_value === undefined
                  ? '—'
                  : String(def.default_value)}
              </td>
              <td>{def.position}</td>
              <td className="row-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => startEditAttribute(def)}
                  disabled={busy}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="danger"
                  onClick={() => deleteAttrMutation.mutate(def.id)}
                  disabled={busy}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {attrForm === null ? (
        <button type="button" className="secondary" onClick={startAddAttribute} disabled={busy}>
          + Add attribute
        </button>
      ) : (
        <form className="attr-form-grid" onSubmit={handleAttributeSubmit}>
          <label className="field">
            Key
            <input
              type="text"
              value={attrForm.key}
              onChange={(e) => setAttrForm({ ...attrForm, key: e.target.value })}
              disabled={attrForm.editId !== null}
              aria-label="Attribute key"
            />
          </label>
          <label className="field">
            Label
            <input
              type="text"
              value={attrForm.label}
              onChange={(e) => setAttrForm({ ...attrForm, label: e.target.value })}
              aria-label="Attribute label"
            />
          </label>
          <label className="field">
            Data type
            <select
              value={attrForm.data_type}
              onChange={(e) =>
                setAttrForm({ ...attrForm, data_type: e.target.value as AttributeDataType })
              }
              aria-label="Attribute data type"
            >
              {ATTRIBUTE_DATA_TYPES.map((dt) => (
                <option key={dt} value={dt}>
                  {dt}
                </option>
              ))}
            </select>
          </label>
          {attrForm.data_type === 'enum' && (
            <label className="field">
              Options (comma-separated)
              <input
                type="text"
                value={attrForm.optionsText}
                onChange={(e) => setAttrForm({ ...attrForm, optionsText: e.target.value })}
                aria-label="Enum options"
              />
            </label>
          )}
          <label className="field">
            Default value
            <DefaultInput
              dataType={attrForm.data_type}
              optionsText={attrForm.optionsText}
              value={attrForm.defaultRaw}
              onChange={(v) => setAttrForm({ ...attrForm, defaultRaw: v })}
            />
          </label>
          <label className="field">
            Required
            <input
              type="checkbox"
              checked={attrForm.required}
              onChange={(e) => setAttrForm({ ...attrForm, required: e.target.checked })}
              aria-label="Attribute required"
            />
          </label>
          <label className="field">
            Position
            <input
              type="number"
              step={1}
              value={attrForm.position}
              onChange={(e) => setAttrForm({ ...attrForm, position: e.target.value })}
              aria-label="Attribute position"
            />
            <small className="muted">Must be unique per type; blank = auto-assign.</small>
          </label>
          <div className="row-actions">
            <button type="submit" disabled={busy}>
              {attrForm.editId === null ? 'Add' : 'Save'}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={cancelAttribute}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  )
}

/**
 * Render the work-item type registry page for administrators.
 *
 * Offers a form to create new types (name, description, id prefix; attributes
 * are added afterwards per type) and one section per existing type with its
 * attribute definitions and their CRUD forms. The list is cached by TanStack
 * Query under ``work-item-types``; every mutation invalidates it so the UI
 * always reflects the latest server state. Failures (duplicate names, reserved
 * keys, bad defaults) surface in an error banner.
 *
 * @return The work item types page element.
 */
export default function WorkItemTypesPage() {
  const queryClient = useQueryClient()

  const [error, setError] = useState<string | null>(null)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [newPrefix, setNewPrefix] = useState('')

  const typesQuery = useQuery({
    queryKey: ['work-item-types'],
    queryFn: api.listWorkItemTypes,
  })
  const types = typesQuery.data ?? []

  /** Drop the cache so the list refetches after a successful mutation. */
  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ['work-item-types'] })
  }

  const createTypeMutation = useMutation({
    mutationFn: () =>
      api.createWorkItemType({
        name: newName.trim(),
        description: newDescription,
        id_prefix: newPrefix.trim(),
        attributes: [],
      }),
    onSuccess: () => {
      setNewName('')
      setNewDescription('')
      setNewPrefix('')
      setError(null)
      invalidate()
    },
    onError: (err) => setError(messageOf(err)),
  })

  /**
   * Submit the type create form.
   *
   * @param event The form submit event (prevented to skip page reload).
   */
  function handleCreateType(event: FormEvent) {
    event.preventDefault()
    if (!newName.trim() || !newPrefix.trim()) return
    createTypeMutation.mutate()
  }

  return (
    <div className="app-shell">
      <AppHeader back={{ label: '← Modules', to: '/' }} />
      <main className="content">
        <section className="module-list">
          <h2>Work Item Types</h2>

          {error !== null && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <form className="module-create" onSubmit={handleCreateType}>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Type name (e.g. task)"
              aria-label="New type name"
              required
            />
            <input
              type="text"
              value={newPrefix}
              onChange={(e) => setNewPrefix(e.target.value)}
              placeholder="ID prefix (e.g. TASK)"
              aria-label="New type id prefix"
              required
            />
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="Description (optional)"
              aria-label="New type description"
            />
            <button type="submit" disabled={createTypeMutation.isPending}>
              {createTypeMutation.isPending ? 'Creating…' : 'Create'}
            </button>
          </form>

          {typesQuery.isPending ? (
            <p className="muted">Loading…</p>
          ) : types.length === 0 ? (
            <p className="muted">No work item types yet. Create the first one above.</p>
          ) : (
            types.map((type) => (
              <TypeSection key={type.id} type={type} reportError={setError} />
            ))
          )}
        </section>
      </main>
    </div>
  )
}

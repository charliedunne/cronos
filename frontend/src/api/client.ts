/** Minimal fetch-based client for the Cronos REST API.
 *
 * All calls go to the same origin (the Vite dev server proxies ``/api`` to
 * the backend), so the httpOnly session cookie is attached automatically.
 */

import type {
  AttributeDefinition,
  AttributeDefinitionOut,
  Module,
  User,
  WorkItem,
  WorkItemCreate,
  WorkItemUpdate,
  WorkItemType,
  WorkItemTypeCreate,
  WorkItemTypeUpdate,
} from './types'

const API_BASE = '/api/v1'

/** Error raised for non-2xx API responses. */
export class ApiError extends Error {
  /** HTTP status code of the failed response. */
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Perform an API request and decode its JSON body.
 *
 * @param path Path relative to the API base (e.g. ``/auth/me``).
 * @param init Optional fetch initialization (method, body, ...).
 * @return The decoded JSON payload typed as ``T``.
 * @throws ApiError when the response status is not 2xx.
 */
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'same-origin',
    ...init,
    headers,
  })

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`
    try {
      const body = (await res.json()) as { detail?: unknown }
      if (typeof body.detail === 'string') {
        detail = body.detail
      } else if (body.detail && typeof body.detail === 'object') {
        // Validation errors arrive as {"detail": {"errors": [...]}}.
        const errors = (body.detail as { errors?: unknown }).errors
        if (Array.isArray(errors) && errors.length > 0) {
          detail = errors.map((e) => String(e)).join('; ')
        }
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new ApiError(res.status, detail)
  }

  // DELETE and other 204 responses carry no body.
  if (res.status === 204) {
    return undefined as T
  }
  return (await res.json()) as T
}

/** Authenticated API operations used by the frontend. */
export const api = {
  /**
   * Fetch the profile of the currently authenticated user.
   *
   * @return The caller's public profile.
   * @throws ApiError 401 when no valid session exists.
   */
  me: () => request<User>('/auth/me'),

  /**
   * Authenticate with username and password; sets the session cookie.
   *
   * @param username Account username.
   * @param password Account password.
   * @return The authenticated user's public profile.
   * @throws ApiError 401 for invalid credentials (generic detail).
   */
  login: (username: string, password: string) =>
    request<User>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  /**
   * Revoke the current session and clear the cookie.
   *
   * @return A short confirmation payload.
   */
  logout: () => request<{ status: string }>('/auth/logout', { method: 'POST' }),

  /**
   * List all modules, ordered by name.
   *
   * @return Every module the caller may see.
   */
  listModules: () => request<Module[]>('/modules'),

  /**
   * Create a module with a unique name.
   *
   * @param name The requested module name.
   * @return The created module.
   * @throws ApiError 409 when the name is already in use.
   */
  createModule: (name: string) =>
    request<Module>('/modules', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  /**
   * Rename a module.
   *
   * @param id The module to rename.
   * @param name The new unique name.
   * @return The updated module.
   * @throws ApiError 409 when the new name is already in use.
   */
  renameModule: (id: number, name: string) =>
    request<Module>(`/modules/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  /**
   * Delete a module that contains no work items.
   *
   * @param id The module to delete.
   * @throws ApiError 409 when the module still contains work items.
   */
  deleteModule: (id: number) => request<void>(`/modules/${id}`, { method: 'DELETE' }),

  /**
   * List a module's work items with type, attribute values, and lock state.
   *
   * @param moduleId The module whose work items to list.
   * @return The module's work items ordered by identifier sequence.
   * @throws ApiError 404 when no such module exists.
   */
  listWorkItems: (moduleId: number) =>
    request<WorkItem[]>(`/modules/${moduleId}/work-items`),

  /**
   * Create a work item of the chosen type; the system assigns its identifier.
   *
   * @param moduleId The module to create the work item in.
   * @param payload The chosen type, a non-empty title, and attribute values.
   * @return The created work item with its assigned identifier.
   * @throws ApiError 404 for an unknown module or type, 422 when attribute
   *         values do not conform to the type's definitions.
   */
  createWorkItem: (moduleId: number, payload: WorkItemCreate) =>
    request<WorkItem>(`/modules/${moduleId}/work-items`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /**
   * Update a locked work item's title and/or attribute values.
   *
   * @param id The work item to update.
   * @param payload The changes (supplied attributes are merged over the
   *         stored ones; the complete map must conform).
   * @return The updated work item (the lock is retained).
   * @throws ApiError 409 when the caller does not hold the lock, or 422 for
   *         non-conforming attribute values.
   */
  updateWorkItem: (id: number, payload: WorkItemUpdate) =>
    request<WorkItem>(`/work-items/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  /**
   * Delete a work item; only the lock holder may do so.
   *
   * @param id The work item to delete.
   * @throws ApiError 409 when the caller does not hold the lock.
   */
  deleteWorkItem: (id: number) => request<void>(`/work-items/${id}`, { method: 'DELETE' }),

  /**
   * Acquire the exclusive editing lock on a work item.
   *
   * @param id The work item to lock.
   * @return The work item with its new lock state (caller as holder).
   * @throws ApiError 409 when the work item is already locked.
   */
  lockWorkItem: (id: number) =>
    request<WorkItem>(`/work-items/${id}/lock`, { method: 'POST' }),

  /**
   * Release the editing lock on a work item the caller holds.
   *
   * @param id The work item to unlock.
   * @throws ApiError 409 when the work item is not locked, or 403 when the
   *         caller is not the holder.
   */
  unlockWorkItem: (id: number) =>
    request<void>(`/work-items/${id}/lock`, { method: 'DELETE' }),

  /**
   * Force-release the editing lock on a work item, regardless of holder.
   *
   * @param id The work item whose lock to release.
   * @return The work item with its (now empty) lock state.
   * @throws ApiError 403 when the caller is not an administrator, or 409
   *         when the work item is not locked.
   */
  forceReleaseWorkItem: (id: number) =>
    request<WorkItem>(`/work-items/${id}/force-release`, { method: 'POST' }),

  /**
   * List every work-item type with its attribute definitions.
   *
   * Open to any authenticated user: the element-creation UI needs the type
   * catalog to render its dynamic form.
   *
   * @return All types ordered by name.
   */
  listWorkItemTypes: () => request<WorkItemType[]>('/work-item-types'),

  /**
   * Create a work-item type with its initial attribute definitions (admin-only).
   *
   * @param payload The type's name, description, id prefix, and attributes.
   * @return The created type with its attributes.
   * @throws ApiError 409 when the name or an attribute key already exists,
   *         422 for invalid definitions, or 403 for non-administrators.
   */
  createWorkItemType: (payload: WorkItemTypeCreate) =>
    request<WorkItemType>('/work-item-types', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /**
   * Modify a work-item type's name, description, or id prefix (admin-only).
   *
   * @param id The type to modify.
   * @param payload The fields to change (omitted fields are untouched).
   * @return The updated type.
   * @throws ApiError 403 when changing a built-in type's name or prefix,
   *         409 on a rename collision, or 403 for non-administrators.
   */
  updateWorkItemType: (id: number, payload: WorkItemTypeUpdate) =>
    request<WorkItemType>(`/work-item-types/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  /**
   * Delete a work-item type that has no work items (admin-only).
   *
   * @param id The type to delete.
   * @throws ApiError 403 for built-in types, 409 when the type still has
   *         work items, or 403 for non-administrators.
   */
  deleteWorkItemType: (id: number) =>
    request<void>(`/work-item-types/${id}`, { method: 'DELETE' }),

  /**
   * Add an attribute definition to a work-item type (admin-only).
   *
   * @param typeId The type to extend.
   * @param payload The attribute's key, label, data type, and options.
   * @return The created attribute definition.
   * @throws ApiError 409 when the key already exists on the type, or 422 for
   *         invalid definitions (reserved keys, bad defaults).
   */
  createAttribute: (typeId: number, payload: AttributeDefinition) =>
    request<AttributeDefinitionOut>(`/work-item-types/${typeId}/attributes`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /**
   * Modify an attribute definition; its key is immutable (admin-only).
   *
   * @param typeId The type owning the attribute.
   * @param attributeId The attribute definition to modify.
   * @param payload The new field values (the key must match the existing one).
   * @return The updated attribute definition.
   * @throws ApiError 422 when the key is changed or a default is invalid.
   */
  updateAttribute: (typeId: number, attributeId: number, payload: AttributeDefinition) =>
    request<AttributeDefinitionOut>(`/work-item-types/${typeId}/attributes/${attributeId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  /**
   * Remove an attribute definition from a type; stored values for the key
   * are stripped from all work items of that type (admin-only).
   *
   * @param typeId The type owning the attribute.
   * @param attributeId The attribute definition to remove.
   */
  deleteAttribute: (typeId: number, attributeId: number) =>
    request<void>(`/work-item-types/${typeId}/attributes/${attributeId}`, { method: 'DELETE' }),

  /**
   * List every user account with role and active state (admin-only).
   *
   * @return All users ordered by username.
   * @throws ApiError 403 when the caller is not an administrator.
   */
  listUsers: () => request<User[]>('/users'),

  /**
   * Create a new (non-admin) user account (admin-only).
   *
   * @param username The requested unique username.
   * @param password The initial password for the account.
   * @return The created user's public profile.
   * @throws ApiError 409 when the username is already taken, or 403 for
   *         non-administrators.
   */
  createUser: (username: string, password: string) =>
    request<User>('/users', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),

  /**
   * Disable a user account, blocking login and existing sessions (admin-only).
   *
   * @param id The account to disable.
   * @return The updated user's public profile.
   * @throws ApiError 404 when no such user exists, or 403 for non-admins.
   */
  disableUser: (id: number) => request<User>(`/users/${id}/disable`, { method: 'POST' }),

  /**
   * Re-enable a previously disabled user account (admin-only).
   *
   * @param id The account to re-enable.
   * @return The updated user's public profile.
   * @throws ApiError 404 when no such user exists, or 403 for non-admins.
   */
  enableUser: (id: number) => request<User>(`/users/${id}/enable`, { method: 'POST' }),
}

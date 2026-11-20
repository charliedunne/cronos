/** Minimal fetch-based client for the Cronos REST API.
 *
 * All calls go to the same origin (the Vite dev server proxies ``/api`` to
 * the backend), so the httpOnly session cookie is attached automatically.
 */

import type { Module, Requirement, RequirementCreate, RequirementUpdate, User } from './types'

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
   * Delete a module that contains no requirements.
   *
   * @param id The module to delete.
   * @throws ApiError 409 when the module still contains requirements.
   */
  deleteModule: (id: number) =>
    request<void>(`/modules/${id}`, { method: 'DELETE' }),

  /**
   * List the requirements of a module with attributes and lock state.
   *
   * @param moduleId The module whose requirements to list.
   * @return The module's requirements ordered by identifier.
   * @throws ApiError 404 when no such module exists.
   */
  listRequirements: (moduleId: number) =>
    request<Requirement[]>(`/modules/${moduleId}/requirements`),

  /**
   * Create a requirement in a module; the system assigns its identifier.
   *
   * @param moduleId The module to create the requirement in.
   * @param payload Title, text, and optional status/priority overrides.
   * @return The created requirement with its assigned identifier.
   * @throws ApiError 422 for an empty title or invalid enum values.
   */
  createRequirement: (moduleId: number, payload: RequirementCreate) =>
    request<Requirement>(`/modules/${moduleId}/requirements`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  /**
   * Update the attributes of a requirement the caller has locked.
   *
   * @param id The requirement to update.
   * @param payload The attribute changes (omitted fields are untouched).
   * @return The updated requirement (the lock is retained).
   * @throws ApiError 409 when the caller does not hold the lock.
   */
  updateRequirement: (id: number, payload: RequirementUpdate) =>
    request<Requirement>(`/requirements/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  /**
   * Acquire the exclusive editing lock on a requirement.
   *
   * @param id The requirement to lock.
   * @return The requirement with its new lock state (caller as holder).
   * @throws ApiError 409 when the requirement is already locked.
   */
  lockRequirement: (id: number) =>
    request<Requirement>(`/requirements/${id}/lock`, { method: 'POST' }),

  /**
   * Release the editing lock on a requirement the caller holds.
   *
   * @param id The requirement to unlock.
   * @throws ApiError 409 when the requirement is not locked, or 403 when the
   *         caller is not the holder.
   */
  unlockRequirement: (id: number) =>
    request<void>(`/requirements/${id}/lock`, { method: 'DELETE' }),
}

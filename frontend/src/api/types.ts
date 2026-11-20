/** Shared TypeScript types mirroring the backend API payloads. */

/** Public representation of a user (mirrors the backend ``UserOut``). */
export interface User {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
}

/** Public representation of a module (mirrors the backend ``ModuleOut``). */
export interface Module {
  id: number
  name: string
}

/** Allowed requirement status values (spec: requirement-store). */
export const REQUIREMENT_STATUSES = ['draft', 'in-review', 'approved', 'deprecated'] as const

/** Allowed requirement priority values (spec: requirement-store). */
export const REQUIREMENT_PRIORITIES = ['low', 'medium', 'high'] as const

/** A requirement status value. */
export type RequirementStatus = (typeof REQUIREMENT_STATUSES)[number]

/** A requirement priority value. */
export type RequirementPriority = (typeof REQUIREMENT_PRIORITIES)[number]

/** Public representation of a requirement (mirrors the backend ``RequirementOut``). */
export interface Requirement {
  id: number
  /** Stable, unique human-readable identifier (e.g. "REQ-00012"). */
  identifier: string
  title: string
  text: string
  status: RequirementStatus
  priority: RequirementPriority
  /** Username of the current lock holder, or null when unlocked. */
  locked_by: string | null
}

/** Payload for creating a requirement (mirrors ``RequirementCreateRequest``). */
export interface RequirementCreate {
  title: string
  text?: string
  status?: RequirementStatus
  priority?: RequirementPriority
}

/** Payload for updating a requirement; only provided fields change (mirrors ``RequirementUpdateRequest``). */
export interface RequirementUpdate {
  title?: string
  text?: string
  status?: RequirementStatus
  priority?: RequirementPriority
}

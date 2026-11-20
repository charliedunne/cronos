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

/** Data types allowed on attribute definitions (spec: work-items). */
export const ATTRIBUTE_DATA_TYPES = [
  'string',
  'text',
  'integer',
  'boolean',
  'date',
  'enum',
] as const

/** An allowed attribute data type. */
export type AttributeDataType = (typeof ATTRIBUTE_DATA_TYPES)[number]

/** Payload for creating or updating an attribute definition (mirrors ``AttributeDefinitionIn``). */
export interface AttributeDefinition {
  key: string
  label: string
  data_type: AttributeDataType
  /** Allowed values; only set for enum attributes. */
  options: string[] | null
  required: boolean
  /** Applied by the system when a work item omits the key. */
  default_value: unknown
  /** Display order; unique per type. ``null`` = auto-assign (append) on create, unchanged on update. */
  position: number | null
}

/** Public representation of an attribute definition, including its id (mirrors ``AttributeDefinitionOut``). */
export interface AttributeDefinitionOut extends AttributeDefinition {
  id: number
}

/** Nested type summary on a work item (mirrors the nested ``WorkItemTypeOut``). */
export interface WorkItemTypeInfo {
  id: number
  name: string
  id_prefix: string
  is_builtin: boolean
}

/** Public representation of a work item (mirrors the backend ``WorkItemOut``). */
export interface WorkItem {
  id: number
  /** Stable, unique human-readable identifier (e.g. "REQ-00012"). */
  identifier: string
  title: string
  type: WorkItemTypeInfo
  /** Values of the item's per-type attributes, keyed by attribute key. */
  attributes: Record<string, unknown>
  /** Username of the current lock holder, or null when unlocked. */
  locked_by: string | null
}

/** Payload for creating a work item (mirrors ``WorkItemCreateRequest``). */
export interface WorkItemCreate {
  type_id: number
  title: string
  attributes: Record<string, unknown>
}

/** Payload for updating a work item; only provided fields change (mirrors ``WorkItemUpdateRequest``). */
export interface WorkItemUpdate {
  title?: string
  /** Merged over the stored values; the complete map must conform. */
  attributes?: Record<string, unknown>
}

/** Public representation of a work-item type with its attribute definitions (mirrors the registry ``WorkItemTypeOut``). */
export interface WorkItemType {
  id: number
  name: string
  description: string
  id_prefix: string
  is_builtin: boolean
  attributes: AttributeDefinitionOut[]
}

/** Payload for creating a work-item type with its initial attributes. */
export interface WorkItemTypeCreate {
  name: string
  description: string
  id_prefix: string
  attributes: AttributeDefinition[]
}

/** Payload for modifying a work-item type; omitted fields are untouched. */
export interface WorkItemTypeUpdate {
  name?: string
  description?: string
  id_prefix?: string
}

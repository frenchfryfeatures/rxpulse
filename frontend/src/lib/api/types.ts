import type { components } from "./schema";

type S = components["schemas"];

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export type Me = S["MeOut"];
export type Staff = S["StaffOut"];
export type StaffCreate = S["StaffCreate"];
export type RoleAssignmentIn = S["RoleAssignmentIn"];
export type Role = S["RoleOut"];
export type Permission = S["PermissionOut"];
export type Location = S["LocationOut"];
export type Item = S["ItemOut"];
export type ItemCreate = S["ItemCreate"];
export type BatchRow = S["BatchRow"];
export type ExpiryBucket = S["ExpiryBucket"];
export type FefoPreview = S["FefoPreviewOut"];
export type Ledger = S["LedgerOut"];
export type Patient = S["PatientOut"];
export type Order = S["OrderOut"];
export type OrderLine = S["OrderLineOut"];
export type OrderCreate = S["OrderCreate"];
export type PickList = S["PickListOut"];
export type Audit = S["AuditOut"];
export type Dashboard = S["DashboardOut"];
export type DevUser = S["DevUser"];
export type OrderStatus = Order["status"];
export type ExpiryStatus = BatchRow["expiry_status"];

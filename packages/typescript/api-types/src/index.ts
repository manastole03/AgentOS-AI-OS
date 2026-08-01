export type ServiceStatus = "ok" | "degraded";

export interface HealthResponse {
  service: string;
  status: ServiceStatus;
  version: string;
  timestamp: string;
  checks: Record<string, string>;
}

export interface ErrorDetail {
  code: string;
  message: string;
  context?: Record<string, unknown>;
}

export interface ErrorResponse {
  error: ErrorDetail;
  request_id?: string;
}

export interface AccessToken {
  access_token: string;
  token_type: "bearer";
}

export type AccountType =
  "patient" | "doctor" | "hospital" | "insurance" | "admin";
export type UserStatus =
  | "pending_verification"
  | "pending_review"
  | "active"
  | "suspended"
  | "disabled";

export interface UserSummary {
  id: string;
  email: string;
  account_type: AccountType;
  status: UserStatus;
  email_verified: boolean;
  phone_verified: boolean;
  roles: string[];
  patient_id?: string | null;
  tenant_id?: string | null;
}

export type DefinitionKind =
  | "module"
  | "form"
  | "dashboard"
  | "workflow"
  | "content";

export interface ApplicationDefinition {
  id: string;
  tenant_id?: string | null;
  kind: DefinitionKind;
  key: string;
  version: number;
  status: "draft" | "review" | "published" | "retired";
  account_types: AccountType[];
  locale: string;
  schema: Record<string, unknown>;
  presentation: Record<string, unknown>;
  rules: Array<Record<string, unknown>>;
  effective_at?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AppManifest {
  tenant_id: string;
  account_type: AccountType;
  locale: string;
  generated_at: string;
  version: string;
  modules: ApplicationDefinition[];
  forms: ApplicationDefinition[];
  dashboards: ApplicationDefinition[];
  workflows: ApplicationDefinition[];
  content: ApplicationDefinition[];
}

export interface ConsentGrant {
  id: string;
  patient_user_id: string;
  grantee_user_id?: string | null;
  grantee_organization_id?: string | null;
  purpose: string;
  scopes: string[];
  status: string;
  expires_at?: string | null;
  revoked_at?: string | null;
  provenance: Record<string, unknown>;
  created_at: string;
}

export interface WorkflowInstance {
  id: string;
  definition_key: string;
  definition_version: number;
  subject_type: string;
  subject_id: string;
  status: string;
  version: number;
  context: Record<string, unknown>;
  available_actions: string[];
  created_at: string;
  updated_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: UserSummary;
}

export interface ProfileResponse extends UserSummary {
  first_name?: string | null;
  last_name?: string | null;
  legal_name?: string | null;
  license_number?: string | null;
  registration_number?: string | null;
  phone?: string | null;
  date_of_birth?: string | null;
  sex_at_birth?: string | null;
  blood_type?: string | null;
  emergency_contact?: string | null;
  specialty?: string | null;
  affiliation?: string | null;
  license_jurisdiction?: string | null;
  organization_type?: string | null;
  product_types?: string[];
  credentials_verified?: boolean | null;
  avatar_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SessionResponse {
  id: string;
  user_agent?: string | null;
  ip_address?: string | null;
  created_at: string;
  last_used_at?: string | null;
  expires_at: string;
  current: boolean;
}

export interface JobWatchSource {
  id?: string | null;
  source_type: "greenhouse" | "lever" | "ashby";
  board_key: string;
  company_name: string;
  board_url: string;
  enabled: boolean;
  initial_sync_completed_at?: string | null;
  last_scanned_at?: string | null;
  last_error_message?: string | null;
}

export interface JobWatchResponse {
  enabled: boolean;
  email_enabled: boolean;
  destination_email: string;
  check_interval_minutes: number;
  titles: string[];
  sources: JobWatchSource[];
  last_scanned_at?: string | null;
}

export interface PortalRecord {
  id: string;
  category: string;
  title: string;
  status: string;
  patient_user_id?: string | null;
  assigned_user_id?: string | null;
  external_reference?: string | null;
  occurred_at?: string | null;
  due_at?: string | null;
  amount_cents?: number | null;
  currency?: string | null;
  data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface DashboardMetric {
  label: string;
  value: number;
  trend: string;
  tone: string;
}

export interface PortalDashboard {
  account_type: AccountType;
  display_name: string;
  metrics: DashboardMetric[];
  recent: PortalRecord[];
  unread_notifications: number;
  integrations: Record<string, boolean>;
}

export interface PortalNotification {
  id: string;
  channel: string;
  severity: string;
  title: string;
  body: string;
  action_url?: string | null;
  read_at?: string | null;
  delivered_at?: string | null;
  created_at: string;
}

export interface JobWatchUpdate {
  enabled?: boolean;
  email_enabled?: boolean;
  check_interval_minutes?: number;
  titles?: string[];
  source_inputs?: string[];
}

export interface DocumentAsset {
  id: string;
  category: string;
  filename: string;
  content_type: string;
  byte_size: number;
  status: string;
  ocr_text?: string | null;
  fhir_resource_type?: string | null;
  fhir_resource_id?: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

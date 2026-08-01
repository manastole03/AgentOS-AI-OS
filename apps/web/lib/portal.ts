import type { AccountType } from "@healthos/api-types";
import type { LucideIcon } from "lucide-react";
import {
  workspaceRoutesFor,
  type WorkspaceRoute,
} from "@/lib/role-routes";
import {
  Activity,
  BadgeDollarSign,
  BedDouble,
  Bell,
  BookOpenText,
  Bot,
  Building2,
  CalendarDays,
  ChartNoAxesCombined,
  ClipboardCheck,
  CreditCard,
  FileCheck2,
  FileClock,
  FileHeart,
  FileText,
  FlaskConical,
  HeartPulse,
  History,
  Hospital,
  IdCard,
  Landmark,
  LayoutDashboard,
  MonitorCog,
  Pill,
  ReceiptText,
  SearchCheck,
  Settings,
  ShieldCheck,
  ShieldQuestion,
  Stethoscope,
  Syringe,
  UserCog,
  Users,
  UsersRound,
} from "lucide-react";

export interface PortalModule {
  slug: string;
  label: string;
  description: string;
  icon: LucideIcon;
  noun: string;
}

export interface WorkflowField {
  key: string;
  label: string;
  placeholder: string;
  type?: "text" | "number";
}

const fields = (
  ...items: Array<[string, string, string, WorkflowField["type"]?]>
) =>
  items.map(([key, label, placeholder, type]) => ({
    key,
    label,
    placeholder,
    type,
  }));

export const workflowFields: Record<string, WorkflowField[]> = {
  vitals: fields(
    ["weight_kg", "Weight (kg)", "e.g. 72.5", "number"],
    ["height_cm", "Height (cm)", "e.g. 175", "number"],
    ["bmi", "BMI", "Calculated or measured", "number"],
    ["blood_pressure", "Blood pressure", "e.g. 120/80"],
    ["heart_rate", "Heart rate", "Beats per minute", "number"],
    [
      "oxygen_saturation",
      "Oxygen saturation / blood gas",
      "SpO₂ or CO₂ reading",
    ],
  ),
  allergies: fields(
    ["allergen", "Allergen", "Medication, food, or environmental"],
    ["reaction", "Reaction", "Observed reaction"],
    ["severity", "Severity", "Mild, moderate, severe"],
  ),
  medical_history: fields(
    ["condition", "Condition or procedure", "e.g. Hypertension"],
    ["clinical_code", "Clinical code", "ICD-10 or SNOMED"],
    ["provider", "Provider", "Treating organization"],
  ),
  vaccinations: fields(
    ["vaccine", "Vaccine", "e.g. Influenza"],
    ["dose", "Dose", "Dose number"],
    ["lot_number", "Lot number", "Manufacturer lot"],
    [
      "certificate_document_id",
      "Certificate document ID",
      "Attached dose certificate",
    ],
  ),
  visits: fields(
    ["doctor", "Doctor", "Treating clinician"],
    ["diagnosis", "Diagnosis", "Clinician-confirmed diagnosis"],
    ["prescription", "Prescription", "Prescription reference"],
    ["medicines", "Prescribed medicines", "Medicine and course details"],
  ),
  medications: fields(
    ["medicine", "Medicine", "Generic or brand name"],
    ["dosage", "Dosage", "Dose and form"],
    ["times", "Daily reminder times", "e.g. 08:00, 20:00"],
    ["course_end", "Course end date", "YYYY-MM-DD"],
  ),
  appointments: fields(
    ["provider", "Provider", "Clinician or facility"],
    ["location", "Location", "Clinic or telehealth"],
    ["visit_type", "Visit type", "Consultation, follow-up…"],
  ),
  lab_reports: fields(
    ["test_name", "Test", "e.g. Hemoglobin A1c"],
    ["result", "Result", "Result with units"],
    ["reference_range", "Reference range", "Laboratory range"],
  ),
  lab_bookings: fields(
    ["test_name", "Lab test", "Available test"],
    ["laboratory", "Laboratory", "Participating lab"],
    ["slot", "Available slot", "Selected real-time slot"],
  ),
  insurance: fields(
    ["payer", "Payer", "Insurance organization"],
    ["member_id", "Member ID", "Member identifier"],
    ["plan_name", "Plan", "Plan or product name"],
    [
      "plain_language_coverage",
      "Coverage explained",
      "Plain-language benefits summary",
    ],
    [
      "recommended_for",
      "Recommended profile tags",
      "Comma-separated matching criteria",
    ],
    [
      "excluded_conditions",
      "Enrollment exclusions",
      "Comma-separated insurer exclusions",
    ],
  ),
  buy_insurance: fields(
    ["plan_name", "Selected plan", "Marketplace policy"],
    ["payer", "Payer", "Participating insurer"],
    ["loyalty_points_used", "Loyalty points", "Points applied", "number"],
  ),
  loyalty_points: fields(
    ["source", "Earned from", "Appointment, wellness activity, renewal…"],
    ["points", "Points", "Points earned", "number"],
  ),
  cost_estimates: fields(
    ["service_code", "Service or procedure", "CPT/HCPCS or plain description"],
    ["provider", "Provider", "Selected provider or facility"],
    [
      "estimated_patient_cost",
      "Estimated patient cost",
      "Estimate, not a guarantee",
    ],
  ),
  claims: fields(
    ["claim_number", "Claim number", "Payer claim reference"],
    ["payer", "Payer", "Insurance organization"],
    ["service_code", "Service code", "CPT/HCPCS code"],
  ),
  health_reminders: fields(
    ["reminder_type", "Reminder type", "Screening, medication…"],
    ["frequency", "Frequency", "Once, daily, annually…"],
  ),
  consents: fields(
    [
      "grantee_user_id",
      "Provider or organization user ID",
      "Authorized HealthOS user UUID",
    ],
    [
      "scopes",
      "Allowed record types",
      "Comma-separated scopes, e.g. visits,lab_reports",
    ],
    ["purpose", "Purpose", "Treatment, payment, or operations"],
  ),
  schedule: fields(
    ["specialty", "Specialty", "e.g. Orthopedics"],
    ["location", "Location", "Clinic room or telehealth"],
    ["visit_type", "Visit type", "Consultation type"],
  ),
  patients: fields(
    ["patient_id", "Patient ID", "15-character HealthOS ID"],
    ["care_program", "Care program", "Assigned care program"],
    ["risk_level", "Risk level", "Low, moderate, high"],
  ),
  prescriptions: fields(
    ["patient_id", "HealthOS Patient ID", "PAT…"],
    ["medication", "Medication", "Generic or brand name"],
    ["dosage", "Dosage", "Dose and form"],
    ["frequency", "Frequency", "Administration schedule"],
  ),
  documentation: fields(
    ["patient_id", "HealthOS Patient ID", "PAT…"],
    ["note_type", "Note type", "Progress, discharge, consult…"],
    ["encounter_id", "Encounter ID", "Associated encounter"],
  ),
  medical_coding: fields(
    ["patient_id", "HealthOS Patient ID", "PAT…"],
    ["encounter_id", "Encounter ID", "Associated encounter"],
    [
      "suggested_codes",
      "Suggested codes",
      "ICD-10, CPT, HCPCS for human review",
    ],
  ),
  referrals: fields(
    ["patient_id", "HealthOS Patient ID", "PAT…"],
    ["specialty", "Referred specialty", "e.g. Orthopedics"],
    ["reason", "Referral reason", "Clinical reason"],
  ),
  care_coordination: fields(
    ["patient_id", "HealthOS Patient ID", "PAT…"],
    ["care_plan", "Care plan", "Coordination plan"],
    ["next_action", "Next action", "Owner and due date"],
  ),
  telemedicine: fields(
    ["provider", "Provider", "Clinician"],
    ["session_url", "Secure session URL", "Video visit link"],
    ["follow_up", "Follow-up plan", "Post-visit summary"],
  ),
  staff: fields(
    ["employee_id", "Employee ID", "Workforce identifier"],
    ["role", "Role", "Clinical or operational role"],
    ["department", "Department", "Assigned department"],
  ),
  departments: fields(
    ["department_code", "Department code", "Internal code"],
    ["service_line", "Service line", "Clinical service line"],
    ["leader", "Department leader", "Responsible leader"],
  ),
  beds: fields(
    ["unit", "Unit", "Care unit"],
    ["room", "Room", "Room number"],
    ["bed_number", "Bed", "Bed identifier"],
  ),
  billing: fields(
    ["invoice_number", "Invoice", "Invoice reference"],
    ["payer", "Payer", "Patient or insurer"],
    ["service_code", "Service code", "Billing code"],
  ),
  resources: fields(
    ["resource_type", "Resource type", "Room, equipment, operating theater…"],
    ["capacity", "Capacity", "Available capacity", "number"],
    ["location", "Location", "Facility location"],
  ),
  service_catalog: fields(
    ["service_code", "Service code", "Internal/CPT code"],
    ["service_name", "Service", "Patient-facing service name"],
    ["availability", "Availability", "Hours or slot rules"],
  ),
  lab_slots: fields(
    ["test_code", "Test code", "Laboratory test identifier"],
    ["test_name", "Test", "Patient-facing test name"],
    ["location", "Location", "Laboratory location"],
    ["price", "Price", "Pre-insurance price", "number"],
  ),
  revenue_cycle: fields(
    ["stage", "Revenue cycle stage", "Charge, coding, claim, payment…"],
    ["owner", "Owner", "Responsible team"],
    ["days_outstanding", "Days outstanding", "Age", "number"],
  ),
  reports: fields(
    ["report_type", "Report type", "Quality, financial, census…"],
    ["period", "Reporting period", "e.g. Q2 2026"],
  ),
  policies: fields(
    ["policy_number", "Policy number", "Policy identifier"],
    ["plan_name", "Plan", "Product name"],
    ["payer", "Payer", "Insurance company"],
    ["coverage_type", "Coverage type", "HMO, PPO, dental…"],
    [
      "plain_language_coverage",
      "Plain-language coverage",
      "Benefits, limits, exclusions, and member actions in clear language",
    ],
  ),
  eligibility: fields(
    ["member_id", "Member ID", "Member identifier"],
    ["plan_name", "Plan", "Plan name"],
    ["coverage_date", "Coverage date", "Date being verified"],
  ),
  prior_authorization: fields(
    ["member_id", "Member ID", "Member identifier"],
    ["service_code", "Service code", "Requested service"],
    ["clinical_rationale", "Clinical rationale", "Evidence summary"],
  ),
  fraud_detection: fields(
    ["case_number", "Case number", "Investigation reference"],
    ["risk_score", "Risk score", "0-100", "number"],
    ["signal_type", "Signal", "Anomaly or rule triggered"],
  ),
  escalations: fields(
    ["source", "Source", "Patient, provider, payer…"],
    ["priority", "Priority", "Routine, urgent, critical"],
    ["owner", "Owner", "Assigned operator"],
  ),
  support: fields(
    ["requester", "Requester", "Account or contact"],
    ["channel", "Channel", "Phone, email, portal"],
    ["resolution", "Resolution", "Support outcome"],
  ),
};

const createModule = (
  slug: string,
  label: string,
  description: string,
  icon: LucideIcon,
  noun = label,
) => ({ slug, label, description, icon, noun });

export const moduleCatalog: Record<string, PortalModule> = {
  vitals: createModule(
    "vitals",
    "Vitals & growth",
    "Longitudinal weight, height, BMI, blood pressure, and blood-gas measures",
    Activity,
    "vital reading",
  ),
  allergies: createModule(
    "allergies",
    "Allergies",
    "Maintained allergy and reaction list",
    ShieldQuestion,
    "allergy",
  ),
  medical_history: createModule(
    "medical_history",
    "Medical history",
    "Conditions, procedures, allergies, and care events",
    History,
    "history item",
  ),
  vaccinations: createModule(
    "vaccinations",
    "Vaccinations",
    "Immunization record and upcoming doses",
    Syringe,
    "vaccination",
  ),
  visits: createModule(
    "visits",
    "Visit timeline",
    "Checkups, clinicians, diagnoses, prescriptions, and medicines",
    Stethoscope,
    "visit",
  ),
  medications: createModule(
    "medications",
    "Medications",
    "Medication courses and timed daily reminders",
    Pill,
    "medication course",
  ),
  appointments: createModule(
    "appointments",
    "Appointments",
    "Upcoming and completed visits",
    CalendarDays,
    "appointment",
  ),
  lab_reports: createModule(
    "lab_reports",
    "Lab reports",
    "Diagnostic results and longitudinal trends",
    FlaskConical,
    "lab report",
  ),
  lab_bookings: createModule(
    "lab_bookings",
    "Book lab tests",
    "Test availability and laboratory slots",
    FlaskConical,
    "lab booking",
  ),
  insurance: createModule(
    "insurance",
    "Insurance",
    "Coverage summary and member information",
    ShieldCheck,
    "coverage item",
  ),
  buy_insurance: createModule(
    "buy_insurance",
    "Buy insurance",
    "History-aware policy marketplace and loyalty benefits",
    Landmark,
    "policy purchase",
  ),
  loyalty_points: createModule(
    "loyalty_points",
    "Loyalty points",
    "Earned benefits available for policy purchases",
    BadgeDollarSign,
    "points activity",
  ),
  cost_estimates: createModule(
    "cost_estimates",
    "Cost estimates",
    "Pre-service coverage and patient-cost estimates",
    BadgeDollarSign,
    "estimate",
  ),
  claims: createModule(
    "claims",
    "Claims",
    "Submission, adjudication, and status tracking",
    ReceiptText,
    "claim",
  ),
  payments: createModule(
    "payments",
    "Payments",
    "Balances, statements, and secure payments",
    CreditCard,
    "payment",
  ),
  notifications: createModule(
    "notifications",
    "Notifications",
    "Clinical and operational updates",
    Bell,
    "notification",
  ),
  health_reminders: createModule(
    "health_reminders",
    "Health reminders",
    "Preventive care and medication reminders",
    HeartPulse,
    "reminder",
  ),
  consents: createModule(
    "consents",
    "Consent & access",
    "Grant, review, and revoke provider access to your record",
    ShieldCheck,
    "consent grant",
  ),
  schedule: createModule(
    "schedule",
    "Schedule",
    "Clinic schedule and visit workload",
    CalendarDays,
    "schedule item",
  ),
  patients: createModule(
    "patients",
    "Patients",
    "Assigned patient panel and care context",
    UsersRound,
    "patient",
  ),
  prescriptions: createModule(
    "prescriptions",
    "Prescriptions",
    "Medication orders and refill workflows",
    Pill,
    "prescription",
  ),
  documentation: createModule(
    "documentation",
    "Documentation",
    "Clinical notes, attestations, and coding",
    BookOpenText,
    "clinical note",
  ),
  medical_coding: createModule(
    "medical_coding",
    "Medical coding",
    "Human-reviewed ICD, CPT, and HCPCS coding assistance",
    FileCheck2,
    "coding task",
  ),
  referrals: createModule(
    "referrals",
    "Referrals",
    "Referral and specialist coordination",
    UsersRound,
    "referral",
  ),
  care_coordination: createModule(
    "care_coordination",
    "Care coordination",
    "Shared care plans and follow-up ownership",
    HeartPulse,
    "care plan",
  ),
  telemedicine: createModule(
    "telemedicine",
    "Telemedicine",
    "Secure video consultations and follow-up summaries",
    Stethoscope,
    "telemedicine visit",
  ),
  ai_assistant: createModule(
    "ai_assistant",
    "AI Assistant",
    "Evidence-grounded clinical and administrative support",
    Bot,
    "conversation",
  ),
  staff: createModule(
    "staff",
    "Staff",
    "Workforce directory, roles, and availability",
    Users,
    "staff member",
  ),
  departments: createModule(
    "departments",
    "Departments",
    "Service lines and operational ownership",
    Building2,
    "department",
  ),
  beds: createModule(
    "beds",
    "Beds",
    "Capacity, occupancy, and patient flow",
    BedDouble,
    "bed",
  ),
  resources: createModule(
    "resources",
    "Resources",
    "Rooms, equipment, and clinical capacity",
    Hospital,
    "resource",
  ),
  service_catalog: createModule(
    "service_catalog",
    "Service catalog",
    "Bookable clinical services, tests, and availability",
    BookOpenText,
    "service",
  ),
  lab_slots: createModule(
    "lab_slots",
    "Lab availability",
    "Real-time laboratory test slots and capacity",
    FlaskConical,
    "lab slot",
  ),
  billing: createModule(
    "billing",
    "Billing",
    "Revenue cycle and outstanding balances",
    BadgeDollarSign,
    "billing item",
  ),
  revenue_cycle: createModule(
    "revenue_cycle",
    "Revenue cycle",
    "Charges, coding, claims, denials, and collections",
    BadgeDollarSign,
    "revenue item",
  ),
  reports: createModule(
    "reports",
    "Reports",
    "Clinical quality and operating reports",
    ChartNoAxesCombined,
    "report",
  ),
  policies: createModule(
    "policies",
    "Policies",
    "Plan products, benefits, and coverage rules",
    FileHeart,
    "policy",
  ),
  eligibility: createModule(
    "eligibility",
    "Eligibility",
    "Member coverage verification",
    IdCard,
    "eligibility check",
  ),
  prior_authorization: createModule(
    "prior_authorization",
    "Prior authorization",
    "Requests, evidence, and determinations",
    ClipboardCheck,
    "authorization",
  ),
  fraud_detection: createModule(
    "fraud_detection",
    "Fraud detection",
    "Signals, investigations, and case review",
    SearchCheck,
    "fraud signal",
  ),
  analytics: createModule(
    "analytics",
    "Analytics",
    "Platform adoption and operating intelligence",
    Activity,
    "metric",
  ),
  audit_logs: createModule(
    "audit_logs",
    "Audit logs",
    "Security and compliance event trail",
    FileClock,
    "audit event",
  ),
  user_management: createModule(
    "user_management",
    "User management",
    "Accounts, roles, and access status",
    UserCog,
    "user",
  ),
  monitoring: createModule(
    "monitoring",
    "Monitoring",
    "Service health and integration operations",
    MonitorCog,
    "monitor",
  ),
  system_settings: createModule(
    "system_settings",
    "System settings",
    "Platform policy and feature configuration",
    Settings,
    "setting",
  ),
  escalations: createModule(
    "escalations",
    "Escalations",
    "Priority operational and customer escalations",
    ShieldQuestion,
    "escalation",
  ),
  support: createModule(
    "support",
    "Customer support",
    "Support cases, ownership, and resolutions",
    Users,
    "support case",
  ),
  documents: createModule(
    "documents",
    "Documents",
    "Secure files, OCR, and clinical document intelligence",
    FileText,
    "document",
  ),
};

export const roleModules: Record<AccountType, string[]> = {
  patient: [
    "medical_history",
    "vitals",
    "allergies",
    "vaccinations",
    "visits",
    "medications",
    "appointments",
    "telemedicine",
    "lab_reports",
    "lab_bookings",
    "insurance",
    "buy_insurance",
    "loyalty_points",
    "claims",
    "cost_estimates",
    "payments",
    "notifications",
    "health_reminders",
    "consents",
    "documents",
    "ai_assistant",
  ],
  doctor: [
    "schedule",
    "patients",
    "prescriptions",
    "documentation",
    "medical_coding",
    "referrals",
    "care_coordination",
    "telemedicine",
    "lab_reports",
    "appointments",
    "ai_assistant",
    "documents",
  ],
  hospital: [
    "staff",
    "departments",
    "beds",
    "resources",
    "service_catalog",
    "lab_slots",
    "billing",
    "revenue_cycle",
    "eligibility",
    "reports",
    "appointments",
    "documents",
  ],
  insurance: [
    "policies",
    "eligibility",
    "claims",
    "prior_authorization",
    "cost_estimates",
    "fraud_detection",
    "documents",
  ],
  admin: [
    "analytics",
    "audit_logs",
    "user_management",
    "monitoring",
    "system_settings",
    "escalations",
    "support",
    "documents",
  ],
};

export const roleMeta: Record<
  AccountType,
  { label: string; icon: LucideIcon; accent: string }
> = {
  patient: {
    label: "Patient portal",
    icon: Stethoscope,
    accent: "Care workspace",
  },
  doctor: {
    label: "Doctor portal",
    icon: FileCheck2,
    accent: "Clinical workspace",
  },
  hospital: {
    label: "Hospital portal",
    icon: Hospital,
    accent: "Operations workspace",
  },
  insurance: {
    label: "Insurance portal",
    icon: Landmark,
    accent: "Payer workspace",
  },
  admin: {
    label: "Admin portal",
    icon: ShieldQuestion,
    accent: "Platform control",
  },
};

export const dashboardModule = createModule(
  "dashboard",
  "Dashboard",
  "Workspace overview",
  LayoutDashboard,
);

/**
 * The role workspaces, decorated for the sidebar. The routing table itself
 * lives in `lib/role-routes` because the edge middleware shares it and must not
 * pull in an icon library.
 */
export interface WorkspaceNavItem extends WorkspaceRoute {
  icon: LucideIcon;
}

const workspaceIcons: Record<string, LucideIcon> = {
  "/health": HeartPulse,
  "/care": CalendarDays,
  "/insurance": ShieldCheck,
  "/clinic": Stethoscope,
  "/operations": Hospital,
  "/payer": Landmark,
  "/admin": MonitorCog,
};

export const roleWorkspaces: Record<AccountType, WorkspaceNavItem[]> = {
  patient: decorate("patient"),
  doctor: decorate("doctor"),
  hospital: decorate("hospital"),
  insurance: decorate("insurance"),
  admin: decorate("admin"),
};

function decorate(accountType: AccountType): WorkspaceNavItem[] {
  return workspaceRoutesFor(accountType).map((item) => ({
    ...item,
    icon: workspaceIcons[item.href] ?? LayoutDashboard,
  }));
}

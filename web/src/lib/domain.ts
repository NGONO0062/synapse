// Miroir du domaine défini côté API (api/synapse_api/domain/enums.py).

export type Role = "PO" | "TESTEUR" | "ADMIN";

export const ROLE_LABELS: Record<Role, string> = {
  PO: "Product Owner",
  TESTEUR: "Testeur",
  ADMIN: "Administrateur",
};

export const TASK_STATUSES = ["BACKLOG", "TODO", "IN_PROGRESS", "REVIEW", "DONE"] as const;
export type TaskStatus = (typeof TASK_STATUSES)[number];

export const STATUS_LABELS: Record<TaskStatus, string> = {
  BACKLOG: "Backlog",
  TODO: "To do",
  IN_PROGRESS: "In progress",
  REVIEW: "Review",
  DONE: "Done",
};

export const TASK_TYPES = ["FEATURE", "BUGFIX", "DOC"] as const;
export type TaskType = (typeof TASK_TYPES)[number];

export const TYPE_LABELS: Record<TaskType, string> = {
  FEATURE: "Feature",
  BUGFIX: "Bugfix",
  DOC: "Doc",
};

export const TYPE_PREFIXES: Record<TaskType, string> = {
  FEATURE: "FEAT",
  BUGFIX: "BUG",
  DOC: "DOC",
};

export type Casquette =
  | "ORCHESTRATEUR"
  | "BUSINESS_ANALYST"
  | "UX_UI_DESIGNER"
  | "ARCHITECTE"
  | "DEVELOPPEUR"
  | "REVIEWER"
  | "ANALYSTE_TEST"
  | "AUTOMATICIEN"
  | "EXPERT_SECURITE"
  | "DEBOGUEUR"
  | "REDACTEUR"
  | "DEVOPS";

export const CASQUETTES: Record<Casquette, { label: string; initials: string }> = {
  ORCHESTRATEUR: { label: "Orchestrateur", initials: "OR" },
  BUSINESS_ANALYST: { label: "Business Analyst", initials: "BA" },
  UX_UI_DESIGNER: { label: "UX/UI Designer", initials: "UX" },
  ARCHITECTE: { label: "Architecte", initials: "AR" },
  DEVELOPPEUR: { label: "Développeur", initials: "DV" },
  REVIEWER: { label: "Reviewer de code", initials: "RV" },
  ANALYSTE_TEST: { label: "Analyste de test", initials: "QA" },
  AUTOMATICIEN: { label: "Automaticien", initials: "AU" },
  EXPERT_SECURITE: { label: "Expert sécurité", initials: "SE" },
  DEBOGUEUR: { label: "Débogueur", initials: "DB" },
  REDACTEUR: { label: "Rédacteur technique", initials: "RT" },
  DEVOPS: { label: "DevOps", initials: "OP" },
};

export function taskCode(type: TaskType, number: number): string {
  return `${TYPE_PREFIXES[type]}-${String(number).padStart(3, "0")}`;
}

export type PendingDecision = "REPORT" | "PLAN" | "QUESTION" | "ESCALATION" | "RESULT" | "TESTER_CONFIRMATION";

export const DECISION_LABELS: Record<PendingDecision, string> = {
  REPORT: "Reformulation",
  PLAN: "Plan",
  QUESTION: "Question",
  ESCALATION: "À trancher",
  RESULT: "Résultat",
  TESTER_CONFIRMATION: "À confirmer",
};

// Modèles exposés par la passerelle (api : domain/enums.py AI_MODELS).
export const AI_MODELS = [
  { id: "claude-sonnet", label: "Claude Sonnet" },
  { id: "claude-opus", label: "Claude Opus" },
  { id: "gpt", label: "GPT" },
  { id: "gemini", label: "Gemini" },
  { id: "mistral", label: "Mistral" },
] as const;

export const DEFAULT_AI_MODEL = "claude-sonnet";

export function modelLabel(id: string): string {
  return AI_MODELS.find((m) => m.id === id)?.label ?? id;
}

export function casquetteLabel(casquette: string | null | undefined): string {
  return casquette && casquette in CASQUETTES ? CASQUETTES[casquette as Casquette].label : "Agent";
}

export const ENVIRONMENT_LABELS = { STAGING: "Staging", PREPROD: "Préprod", PROD: "Prod" } as const;

export const SEVERITY_LABELS = { BLOQUANT: "Bloquant", MAJEUR: "Majeur", MINEUR: "Mineur" } as const;

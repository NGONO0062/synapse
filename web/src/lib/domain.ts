// Miroir du domaine défini côté API (api/synapse_api/domain/enums.py).

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

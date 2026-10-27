import "server-only";
import { redirect } from "next/navigation";
import { authConfig } from "./auth/config";
import { getAccessToken } from "./auth/current-user";
import type { Casquette, PendingDecision, TaskStatus, TaskType } from "./domain";

// Appels à l'API Synapse depuis le serveur Next, avec le jeton de la session.

async function call(method: string, path: string, body?: unknown): Promise<Response> {
  const response = await fetch(new URL(path, authConfig.apiUrl), {
    method,
    headers: {
      Authorization: `Bearer ${await getAccessToken()}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  if (response.status === 401) redirect("/connexion");
  return response;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await call("GET", path);
  if (!response.ok) throw new Error(`API ${path} : ${response.status}`);
  return response.json() as Promise<T>;
}

/** Lecture qui renvoie null sur 404 (pour afficher notFound()). */
export async function apiFind<T>(path: string): Promise<T | null> {
  const response = await call("GET", path);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`API ${path} : ${response.status}`);
  return response.json() as Promise<T>;
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

/** Écriture : renvoie le message d'erreur de l'API au lieu de lever, pour l'afficher. */
export async function apiSend<T>(method: "POST" | "PUT" | "DELETE", path: string, body?: unknown): Promise<ApiResult<T>> {
  const response = await call(method, path, body);
  if (response.ok) return { ok: true, data: (await response.json()) as T };
  const payload = await response.json().catch(() => null);
  const detail = payload?.detail;
  const error =
    typeof detail === "string"
      ? detail
      : (detail?.message ?? (Array.isArray(detail) ? detail[0]?.msg : null) ?? "L’action a échoué.");
  return { ok: false, error };
}

export type Me = { subject: string; name: string; email: string | null; roles: string[] };

export type Project = { id: string; name: string; description: string; created_at: string };

export type ProjectSummary = Project & {
  status_counts: Record<TaskStatus, number>;
  pending_decisions: number;
};

export type Task = {
  id: string;
  project_id: string;
  code: string;
  type: TaskType;
  title: string;
  description: string;
  status: TaskStatus;
  ai_model: string;
  pending_decision: PendingDecision | null;
  awaiting_human: boolean;
  awaiting_reason: "QUESTION" | "PLAN_CHANGE" | "QA_LIMIT" | "TIMEOUT" | null;
  plan_version: number;
  validated_plan_version: number;
  rejected_plan_version: number;
  qa_round_trips: number;
  result_validated: boolean;
  tester_confirmed: boolean;
  created_at: string;
  updated_at: string;
};

export type Proposal = {
  changes: string[];
  warnings: string[];
  tests: string | null;
  uncertainties: string[];
  assumptions: string[];
  unverified: string[];
};

export type TaskMessage = {
  id: string;
  kind: "MESSAGE" | "PLAN" | "RESULT" | "QUESTION";
  author_kind: "HUMAN" | "AGENT";
  author_name: string;
  casquette: Casquette | null;
  ai_model: string | null;
  body: string;
  payload: Proposal | null;
  plan_version: number | null;
  created_at: string;
};

export type TaskEvent = {
  id: string;
  command: string;
  actor_kind: "HUMAN" | "AGENT";
  actor_name: string;
  casquette: Casquette | null;
  ai_model: string | null;
  from_status: TaskStatus;
  to_status: TaskStatus;
  comment: string | null;
  created_at: string;
};

export type Decision = {
  kind: PendingDecision;
  task: Task;
  project_id: string;
  project_name: string;
  casquette: Casquette | null;
  since: string;
};

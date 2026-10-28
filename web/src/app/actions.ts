"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { apiSend, type Project, type Task } from "@/lib/api";
import { DEFAULT_AI_MODEL } from "@/lib/domain";

// Chaque action passe par l'API, qui revérifie le jeton, le rôle et le cycle de vie.
// Elles renvoient l'erreur à afficher plutôt que de lever.

export type ActionState = { error: string | null };

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

export async function createProject(_: ActionState, form: FormData): Promise<ActionState> {
  const name = text(form, "name");
  if (!name) return { error: "Donne un nom au projet." };
  const result = await apiSend<Project>("POST", "/projects", { name, description: text(form, "description") });
  if (!result.ok) return { error: result.error };
  redirect(`/projets/${result.data.id}`);
}

export async function createTask(projectId: string, _: ActionState, form: FormData): Promise<ActionState> {
  const request = text(form, "request");
  if (!request) return { error: "Décris la demande." };
  // Le titre reprend la première ligne ; le texte complet ouvre le fil.
  const firstLine = request.split("\n")[0];
  const title = firstLine.length > 120 ? `${firstLine.slice(0, 117)}…` : firstLine;
  const result = await apiSend<Task>("POST", `/projects/${projectId}/tasks`, {
    type: text(form, "type") || "FEATURE",
    title,
    description: request,
    ai_model: text(form, "ai_model") || DEFAULT_AI_MODEL,
  });
  if (!result.ok) return { error: result.error };
  redirect(`/projets/${projectId}/taches/${result.data.code}`);
}

/** Écran 6 : signalement structuré d'un bug. */
export async function reportBug(projectId: string, _: ActionState, form: FormData): Promise<ActionState> {
  const fields = ["title", "steps", "expected", "actual"] as const;
  if (fields.some((f) => !text(form, f))) {
    return { error: "Titre, étapes, résultat attendu et résultat obtenu sont obligatoires." };
  }
  const result = await apiSend<Task>("POST", `/projects/${projectId}/bugs`, {
    title: text(form, "title"),
    environment: text(form, "environment") || "STAGING",
    device: text(form, "device"),
    steps: text(form, "steps"),
    expected: text(form, "expected"),
    actual: text(form, "actual"),
    severity: text(form, "severity") || "MAJEUR",
  });
  if (!result.ok) return { error: result.error };
  redirect(`/projets/${projectId}/taches/${result.data.code}`);
}

/** Décision humaine sur une tâche (prioriser, valider, refuser, répondre, confirmer). */
export async function runCommand(
  taskId: string,
  command: string,
  _: ActionState,
  form: FormData,
): Promise<ActionState> {
  const comment = text(form, "comment");
  const result = await apiSend<Task>("POST", `/tasks/${taskId}/commands`, {
    command,
    comment: comment || null,
  });
  if (!result.ok) return { error: result.error };
  refresh();
  return { error: null };
}

export async function postMessage(taskId: string, _: ActionState, form: FormData): Promise<ActionState> {
  const body = text(form, "body");
  if (!body) return { error: null };
  const result = await apiSend("POST", `/tasks/${taskId}/messages`, { body });
  if (!result.ok) return { error: result.error };
  refresh();
  return { error: null };
}

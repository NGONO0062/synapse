"use server";

import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { apiSend, type Project, type Task } from "@/lib/api";

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
  const type = text(form, "type") || "FEATURE";
  const ai_model = text(form, "ai_model");
  // Un bug décrit en quelques mots est reformulé par une casquette, puis validé par son auteur.
  if (type === "BUGFIX") return sendBugInWords(projectId, request, ai_model);
  // Le titre reprend la première ligne ; le texte complet ouvre le fil.
  const firstLine = request.split("\n")[0];
  const title = firstLine.length > 120 ? `${firstLine.slice(0, 117)}…` : firstLine;
  const result = await apiSend<Task>("POST", `/projects/${projectId}/tasks`, {
    type,
    title,
    description: request,
    ...(ai_model ? { ai_model } : {}),
  });
  if (!result.ok) return { error: result.error };
  redirect(`/projets/${projectId}/taches/${result.data.code}`);
}

/** Écran 6 : bug décrit en langage naturel (mode par défaut). */
export async function reportBugInWords(projectId: string, _: ActionState, form: FormData): Promise<ActionState> {
  const description = text(form, "text");
  if (!description) return { error: "Décris le bug en quelques mots." };
  return sendBugInWords(projectId, description, text(form, "ai_model"));
}

// Sans modèle choisi, l'API applique son modèle par défaut.
async function sendBugInWords(projectId: string, description: string, ai_model: string): Promise<ActionState> {
  const result = await apiSend<Task>("POST", `/projects/${projectId}/bugs/text`, {
    text: description,
    ...(ai_model ? { ai_model } : {}),
  });
  if (!result.ok) return { error: result.error };
  redirect(`/projets/${projectId}/taches/${result.data.code}`);
}

/** Écran 6 : signalement structuré d'un bug (formulaire détaillé). */
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

"use client";

import { useActionState, useState } from "react";
import { createProject } from "@/app/actions";
import styles from "./page.module.css";

type Mode = "create" | "import";

export function NewProjectForm() {
  const [mode, setMode] = useState<Mode>("create");
  const [state, formAction, pending] = useActionState(createProject, { error: null });

  return (
    <>
      <div role="tablist" aria-label="Type de projet" className={styles.tabs}>
        <button type="button" role="tab" aria-selected={mode === "create"} onClick={() => setMode("create")}>
          Créer de zéro
        </button>
        <button type="button" role="tab" aria-selected={mode === "import"} onClick={() => setMode("import")}>
          Importer un projet existant
        </button>
      </div>

      {mode === "import" ? (
        <p className={styles.notice} role="tabpanel">
          L’import d’un dépôt existant (étude du code, mémoire reconstituée, reprise du backlog) arrive avec
          l’orchestration des agents.
        </p>
      ) : (
        <form action={formAction} className={styles.form} role="tabpanel">
          <div className={styles.field}>
            <label htmlFor="name">Nom du projet</label>
            <input id="name" name="name" type="text" placeholder="Ex. : Portail de réservation" maxLength={200} required />
          </div>

          <div className={styles.brief}>
            <label htmlFor="description" className="sr-only">
              Description de l’application
            </label>
            <textarea
              id="description"
              name="description"
              rows={5}
              placeholder="Pour qui, quoi faire, les règles métier que tu connais déjà, ce qui est hors périmètre…"
            />
            <div className={styles.briefFooter}>
              <span className={styles.hint}>Les pièces jointes arriveront avec le stockage des documents.</span>
              <button type="submit" className={styles.submit} disabled={pending}>
                Créer le projet
                <svg aria-hidden width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 8h10M9 4l4 4-4 4" />
                </svg>
              </button>
            </div>
          </div>

          {state.error && (
            <p className={styles.error} role="alert">
              {state.error}
            </p>
          )}
        </form>
      )}
    </>
  );
}

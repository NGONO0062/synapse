"use client";

import { useActionState } from "react";
import { setProjectBudget } from "@/app/actions";
import styles from "@/components/usage/usage.module.css";

// Quota mensuel d'un projet. Vide : le quota par défaut de l'espace s'applique.
export function BudgetForm({ projectId, projectName, budget }: { projectId: string; projectName: string; budget: number | null }) {
  const [state, formAction, pending] = useActionState(setProjectBudget.bind(null, projectId), { error: null });
  const id = `budget-${projectId}`;
  return (
    <form action={formAction} className={styles.budgetForm}>
      <label htmlFor={id} className="sr-only">
        Quota mensuel de {projectName}, en dollars
      </label>
      <input
        id={id}
        name="budget"
        inputMode="decimal"
        defaultValue={budget === null ? "" : String(budget).replace(".", ",")}
        placeholder="Défaut"
        aria-describedby={state.error ? `${id}-error` : undefined}
      />
      <button type="submit" disabled={pending}>
        Enregistrer
      </button>
      {state.error && (
        <span id={`${id}-error`} className={styles.formError} role="alert">
          {state.error}
        </span>
      )}
    </form>
  );
}

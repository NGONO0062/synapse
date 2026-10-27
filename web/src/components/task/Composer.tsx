"use client";

import { useActionState, type KeyboardEvent } from "react";
import type { ActionState } from "@/app/actions";
import { AI_MODELS, DEFAULT_AI_MODEL, TYPE_LABELS, type TaskType } from "@/lib/domain";
import styles from "./Composer.module.css";

type Props = {
  action: (state: ActionState, form: FormData) => Promise<ActionState>;
  field: string; // nom du champ texte envoyé à l'action
  label: string;
  placeholder: string;
  taskTypes?: readonly TaskType[]; // sélecteur de type (création de tâche)
  chooseModel?: boolean; // sélecteur de modèle IA (création de tâche)
  modelName?: string; // modèle de la tâche, affiché en lecture seule
};

// Barre de saisie (écrans 4 et 5) : Entrée envoie, Maj+Entrée va à la ligne.
export function Composer({ action, field, label, placeholder, taskTypes, chooseModel, modelName }: Props) {
  const [state, formAction, pending] = useActionState(action, { error: null });

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  }

  return (
    <form action={formAction} className={styles.composer}>
      <div className={styles.box}>
        <label htmlFor={`composer-${field}`} className="sr-only">
          {label}
        </label>
        <textarea
          id={`composer-${field}`}
          name={field}
          rows={1}
          placeholder={placeholder}
          onKeyDown={submitOnEnter}
          disabled={pending}
          required
        />
        <button type="submit" className={styles.send} aria-label="Envoyer" disabled={pending}>
          <svg aria-hidden width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 13V3M3.5 7.5L8 3l4.5 4.5" />
          </svg>
        </button>
      </div>
      <div className={styles.tools}>
        <div className={styles.group}>
          {taskTypes && (
            <>
              <label htmlFor="composer-type" className="sr-only">
                Type de demande
              </label>
              <select id="composer-type" name="type" className={styles.select} defaultValue={taskTypes[0]}>
                {taskTypes.map((t) => (
                  <option key={t} value={t}>
                    {TYPE_LABELS[t]}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
        <div className={styles.group}>
          {chooseModel ? (
            <>
              <label htmlFor="composer-model" className="sr-only">
                Modèle IA
              </label>
              <select id="composer-model" name="ai_model" className={styles.select} defaultValue={DEFAULT_AI_MODEL}>
                {AI_MODELS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </>
          ) : (
            modelName && <span className={styles.strong}>{modelName}</span>
          )}
          <span className={styles.strong}>Validation manuelle</span>
        </div>
      </div>
      {state.error && (
        <p className={styles.error} role="alert">
          {state.error}
        </p>
      )}
    </form>
  );
}

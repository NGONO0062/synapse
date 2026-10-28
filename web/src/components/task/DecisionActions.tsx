"use client";

import { useActionState, useState } from "react";
import { runCommand } from "@/app/actions";
import { Button } from "@/components/ui/Button";
import styles from "./DecisionActions.module.css";

type Props = {
  taskId: string;
  approve: { command: string; label: string };
  // Refus ou demande de modifications : un commentaire est obligatoire.
  reject?: { command: string; label: string; placeholder: string };
  // Boutons pleine largeur, l'un sous l'autre (panneau du livrable).
  stacked?: boolean;
};

// Boutons de décision d'une carte. Le vert est réservé à la décision humaine.
export function DecisionActions({ taskId, approve, reject, stacked = false }: Props) {
  const [approveState, approveAction, approving] = useActionState(runCommand.bind(null, taskId, approve.command), {
    error: null,
  });
  const [rejectState, rejectAction, rejecting] = useActionState(
    runCommand.bind(null, taskId, reject?.command ?? ""),
    { error: null },
  );
  const [commenting, setCommenting] = useState(false);
  const error = approveState.error ?? rejectState.error;
  const row = stacked ? `${styles.row} ${styles.stacked}` : styles.row;

  return (
    <div className={styles.actions}>
      {!commenting && (
        <div className={row}>
          <form action={approveAction}>
            <Button type="submit" variant="human" block={stacked} disabled={approving}>
              {approve.label}
            </Button>
          </form>
          {reject && (
            <Button variant="outline" block={stacked} onClick={() => setCommenting(true)}>
              {reject.label}
            </Button>
          )}
        </div>
      )}
      {reject && commenting && (
        <form action={rejectAction} className={styles.comment}>
          <label htmlFor={`comment-${taskId}`} className="sr-only">
            Ton commentaire
          </label>
          <textarea id={`comment-${taskId}`} name="comment" rows={3} placeholder={reject.placeholder} required autoFocus />
          <div className={row}>
            <Button type="submit" variant="primary" block={stacked} disabled={rejecting}>
              Envoyer le commentaire
            </Button>
            <Button variant="outline" block={stacked} onClick={() => setCommenting(false)}>
              Annuler
            </Button>
          </div>
        </form>
      )}
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

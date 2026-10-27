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
};

// Boutons de décision d'une carte. Le vert est réservé à la décision humaine.
export function DecisionActions({ taskId, approve, reject }: Props) {
  const [approveState, approveAction, approving] = useActionState(runCommand.bind(null, taskId, approve.command), {
    error: null,
  });
  const [rejectState, rejectAction, rejecting] = useActionState(
    runCommand.bind(null, taskId, reject?.command ?? ""),
    { error: null },
  );
  const [commenting, setCommenting] = useState(false);
  const error = approveState.error ?? rejectState.error;

  return (
    <div className={styles.actions}>
      {!commenting && (
        <div className={styles.row}>
          <form action={approveAction}>
            <Button type="submit" variant="human" disabled={approving}>
              {approve.label}
            </Button>
          </form>
          {reject && (
            <Button variant="outline" onClick={() => setCommenting(true)}>
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
          <div className={styles.row}>
            <Button type="submit" variant="primary" disabled={rejecting}>
              Envoyer le commentaire
            </Button>
            <Button variant="outline" onClick={() => setCommenting(false)}>
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

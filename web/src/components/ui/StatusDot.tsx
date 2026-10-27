import { STATUS_LABELS, type TaskStatus } from "@/lib/domain";
import styles from "./StatusDot.module.css";

// Une couleur par statut (jetons --sy-status-*). Source unique pour toute l'interface.
export const STATUS_COLORS: Record<TaskStatus, string> = {
  BACKLOG: "var(--sy-status-backlog)",
  TODO: "var(--sy-status-todo)",
  IN_PROGRESS: "var(--sy-status-in-progress)",
  REVIEW: "var(--sy-status-review)",
  DONE: "var(--sy-status-done)",
};

export function StatusDot({ status, withLabel = false }: { status: TaskStatus; withLabel?: boolean }) {
  return (
    <span className={styles.status}>
      <span className={styles.dot} style={{ background: STATUS_COLORS[status] }} aria-hidden />
      {withLabel ? STATUS_LABELS[status] : <span className="sr-only">{STATUS_LABELS[status]}</span>}
    </span>
  );
}

// Étiquette de statut : pastille et bordure à la couleur du statut, texte toujours lisible.
export function StatusTag({ status }: { status: TaskStatus }) {
  return (
    <span className={styles.tag} style={{ borderColor: STATUS_COLORS[status] }}>
      <span className={styles.dot} style={{ background: STATUS_COLORS[status] }} aria-hidden />
      {STATUS_LABELS[status]}
    </span>
  );
}

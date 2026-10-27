import { STATUS_LABELS, type TaskStatus } from "@/lib/domain";
import styles from "./StatusDot.module.css";

const STATUS_COLORS: Record<TaskStatus, string> = {
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

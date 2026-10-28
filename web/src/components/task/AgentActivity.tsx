import Image from "next/image";
import type { Task, TaskActivity } from "@/lib/api";
import { casquetteLabel } from "@/lib/domain";
import { clockTime, relativeTime } from "@/lib/format";
import styles from "./AgentActivity.module.css";

/** Des casquettes ont du travail sur cette tâche (miroir de api/synapse_api/agents/jobs.py). */
export function agentsAtWork(task: Task): boolean {
  if (task.activity) return true;
  switch (task.status) {
    case "BACKLOG":
      return task.report_required && task.validated_report_version === 0 && task.pending_decision !== "REPORT";
    case "TODO":
      return task.pending_decision === null;
    case "IN_PROGRESS":
      return !task.awaiting_human;
    default:
      return false;
  }
}

// Ce qu'une casquette fait en ce moment : l'humain voit que sa demande est traitée,
// ou pourquoi elle ne l'est pas.
export function AgentActivity({ activity }: { activity: TaskActivity }) {
  const who = casquetteLabel(activity.casquette);
  if (activity.error) {
    return (
      <div className={`${styles.activity} ${styles.blocked}`} role="status">
        <svg aria-hidden width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
          <path d="M9 2.5L16 15H2L9 2.5z" />
          <path d="M9 7.5v3.5M9 13v.01" />
        </svg>
        <div className={styles.text}>
          <p>
            <strong>{who}</strong> ne peut pas avancer : {activity.error}
          </p>
          {activity.retry_at && (
            <p className={styles.meta}>Nouvel essai automatique à {clockTime(activity.retry_at)}.</p>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className={styles.activity} role="status" aria-live="polite">
      <LogoSpinner />
      <p className={styles.text}>
        <strong>{who}</strong> {activity.step}…{" "}
        <span className={styles.meta}>· commencé {relativeTime(activity.updated_at)}</span>
      </p>
    </div>
  );
}

/** Une demande vient de changer d'étape : la casquette va s'y mettre. */
export function AgentPending() {
  return (
    <div className={styles.activity} role="status" aria-live="polite">
      <LogoSpinner />
      <p className={styles.text}>L’orchestrateur confie la suite à une casquette…</p>
    </div>
  );
}

/** Le logo de Synapse qui tourne : une casquette travaille. */
export function LogoSpinner({ small = false }: { small?: boolean }) {
  const size = small ? 14 : 22;
  return <Image src="/logo-light.png" alt="" width={size} height={size} className={styles.spinner} aria-hidden />;
}

import type { Task } from "@/lib/api";
import type { TaskStatus, TaskType } from "@/lib/domain";
import styles from "./TaskChain.module.css";

type Step = { label: string; state: "done" | "active" | "pending"; human: boolean };

// Frise des casquettes du fil (écrans 4 et 5). En attendant l'orchestrateur, l'étape
// active se déduit du statut de la tâche.
const CHAINS: Record<TaskType, { label: string; reachedAt: TaskStatus; human?: boolean }[]> = {
  FEATURE: [
    { label: "Business Analyst", reachedAt: "TODO" },
    { label: "Architecte", reachedAt: "TODO" },
    { label: "Développeur", reachedAt: "IN_PROGRESS" },
    { label: "QA", reachedAt: "IN_PROGRESS" },
    { label: "Sécurité", reachedAt: "IN_PROGRESS" },
    { label: "Documentation", reachedAt: "IN_PROGRESS" },
    { label: "Ta review", reachedAt: "REVIEW", human: true },
  ],
  BUGFIX: [
    { label: "Reproduction", reachedAt: "TODO" },
    { label: "Plan validé", reachedAt: "IN_PROGRESS" },
    { label: "Correction", reachedAt: "IN_PROGRESS" },
    { label: "Ta review", reachedAt: "REVIEW", human: true },
    { label: "Confirmation testeur", reachedAt: "REVIEW", human: true },
  ],
  DOC: [
    { label: "Rédacteur technique", reachedAt: "TODO" },
    { label: "Relecture", reachedAt: "IN_PROGRESS" },
    { label: "Ta review", reachedAt: "REVIEW", human: true },
  ],
};

const ORDER: TaskStatus[] = ["BACKLOG", "TODO", "IN_PROGRESS", "REVIEW", "DONE"];

export function stepsFor(task: Task): Step[] {
  const chain = CHAINS[task.type];
  const current = ORDER.indexOf(task.status);
  const reached = chain.map((s) => ORDER.indexOf(s.reachedAt) <= current);
  let active = reached.lastIndexOf(true);
  if (task.status === "DONE") active = -1;
  // Bugfix validé par le PO : c'est au tour du testeur.
  if (task.type === "BUGFIX" && task.status === "REVIEW") active = task.result_validated ? 4 : 3;
  return chain.map((s, i) => ({
    label: s.label,
    human: Boolean(s.human),
    state: task.status === "DONE" || i < active ? "done" : i === active ? "active" : "pending",
  }));
}

export function TaskChain({ task }: { task: Task }) {
  const steps = stepsFor(task);
  return (
    <ol className={styles.chain} aria-label="Étapes de la tâche">
      {steps.map((step) => (
        <li
          key={step.label}
          className={[styles[step.state], step.human && step.state === "active" && styles.human]
            .filter(Boolean)
            .join(" ")}
          aria-current={step.state === "active" ? "step" : undefined}
        >
          {step.state === "done" && <span aria-hidden>✓ </span>}
          {step.label}
          {step.state === "done" && <span className="sr-only"> (terminé)</span>}
        </li>
      ))}
    </ol>
  );
}

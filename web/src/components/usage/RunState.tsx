import type { EvaluationRun } from "@/lib/api";
import styles from "./usage.module.css";

// État d'un rejeu de cas de référence, en mots (jamais par la seule couleur).
export function RunState({ run }: { run: EvaluationRun }) {
  if (run.status === "RUNNING") return <span className={`${styles.badge} ${styles.badgeNeutral}`}>En cours</span>;
  if (run.status === "ERROR") return <span className={`${styles.badge} ${styles.badgeError}`}>Rejeu interrompu</span>;
  if (run.regressed_cases.length > 0) {
    const n = run.regressed_cases.length;
    return (
      <span className={`${styles.badge} ${styles.badgeRegression}`}>
        {n === 1 ? "1 régression" : `${n} régressions`}
      </span>
    );
  }
  return <span className={`${styles.badge} ${styles.badgeOk}`}>Pas de régression</span>;
}

import { CASQUETTES, type Casquette } from "@/lib/domain";
import styles from "./CasquetteChain.module.css";

export type ChainStep = {
  casquette: Casquette;
  label?: string; // libellé court (ex. « QA ») si différent du nom complet
  state: "done" | "active" | "pending";
};

const STATE_LABELS = { done: "terminé", active: "en cours", pending: "à venir" } as const;

// Frise des casquettes : des nœuds ronds reliés par un trait, comme le logo.
export function CasquetteChain({ steps }: { steps: ChainStep[] }) {
  return (
    <ol className={styles.chain}>
      {steps.map((step) => {
        const casquette = CASQUETTES[step.casquette];
        return (
          <li key={step.casquette} className={`${styles.step} ${styles[step.state]}`}>
            <span className={styles.node} aria-hidden>
              {step.state === "done" ? "✓" : casquette.initials}
            </span>
            {step.label ?? casquette.label}
            <span className="sr-only">, {STATE_LABELS[step.state]}</span>
          </li>
        );
      })}
    </ol>
  );
}

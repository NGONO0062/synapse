import type { Metadata } from "next";
import { Logo } from "@/components/ui/Logo";
import { NewProjectForm } from "./NewProjectForm";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Nouveau projet · Synapse" };

const PIPELINE = [
  { initials: "BA", step: "Exigences", decision: "ta validation" },
  { initials: "UX", step: "Maquettes", decision: "ta validation" },
  { initials: "AR", step: "Architecture", decision: "ta validation" },
  { initials: "DV", step: "Code, revue, tests, sécurité, doc", decision: "ta recette" },
  { initials: "OP", step: "Déploiements", decision: "ta mise en prod" },
];

// Écran 3 · Nouveau projet
export default function NouveauProjetPage() {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <header className={styles.header}>
          <Logo size={64} />
          <h1>Que construit-on ?</h1>
        </header>

        <NewProjectForm />

        <section aria-labelledby="h-pipe" className={styles.pipeline}>
          <h2 id="h-pipe">Pipeline du projet</h2>
          <ol>
            {PIPELINE.map((p) => (
              <li key={p.step} className={styles.stage}>
                <span className={styles.step}>
                  <span className={styles.node} aria-hidden>
                    {p.initials}
                  </span>
                  {p.step}
                </span>
                <span className={styles.decision}>{p.decision}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}

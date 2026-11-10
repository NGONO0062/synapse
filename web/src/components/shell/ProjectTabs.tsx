import Link from "next/link";
import styles from "./ProjectTabs.module.css";

// Onglets d’un projet (maquettes 08 et 09) : retour aux tâches, mémoire du projet.
// « Environnements » viendra avec son lot.
export function ProjectTabs({ projectId, current }: { projectId: string; current: "memoire" }) {
  return (
    <nav aria-label="Projet" className={styles.tabs}>
      <Link href={`/projets/${projectId}`} className={styles.tab}>
        ← Tâches
      </Link>
      <Link
        href={`/projets/${projectId}/memoire`}
        className={styles.tab}
        aria-current={current === "memoire" ? "page" : undefined}
      >
        Mémoire du projet
      </Link>
    </nav>
  );
}

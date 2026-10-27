import Link from "next/link";
import { Suspense } from "react";
import { STATUS_COLORS } from "@/components/ui/StatusDot";
import { Tag, TypeTag } from "@/components/ui/Tag";
import { Logo } from "@/components/ui/Logo";
import { apiGet, type Decision, type ProjectSummary } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { DECISION_LABELS, STATUS_LABELS, TASK_STATUSES, casquetteLabel } from "@/lib/domain";
import { relativeTime } from "@/lib/format";
import styles from "./page.module.css";

// Écran 2 · Accueil : décisions en attente sur tous les projets, puis les projets.
// (Les mises en production rejoindront la liste avec les environnements, lot 4.)
export default function HomePage() {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <Suspense
          fallback={
            <header className={styles.header}>
              <Logo size={64} />
              <h1>Bonjour</h1>
            </header>
          }
        >
          <Home />
        </Suspense>
      </div>
    </main>
  );
}

async function Home() {
  const [user, decisions, projects] = await Promise.all([
    getCurrentUser(),
    apiGet<Decision[]>("/decisions"),
    apiGet<ProjectSummary[]>("/projects"),
  ]);
  const count = decisions.length;
  const subtitle =
    count === 0 ? "Aucune décision ne t’attend." : count === 1 ? "1 décision t’attend." : `${count} décisions t’attendent.`;

  return (
    <>
      <header className={styles.header}>
        <Logo size={64} />
        <h1>Bonjour {user.givenName ?? user.name}</h1>
        <p>{subtitle}</p>
      </header>

      {count > 0 && (
        <section aria-labelledby="h-valid" className={styles.section}>
          <h2 id="h-valid">En attente de ta validation</h2>
          <ul className={styles.decisions}>
            {decisions.map((d) => (
              <li key={d.task.id}>
                <Link href={`/projets/${d.project_id}/taches/${d.task.code}`} className={styles.decision}>
                  <TypeTag type={d.task.type} />
                  <span className={styles.decisionText}>
                    <span className={styles.decisionTitle}>
                      {DECISION_LABELS[d.kind]} · {d.task.title}
                    </span>
                    <span className={styles.meta}>
                      {d.project_name} · {casquetteLabel(d.casquette)} · {relativeTime(d.since)}
                    </span>
                  </span>
                  <span className={styles.cta}>{d.kind === "QUESTION" ? "Répondre" : "Relire"} →</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="h-proj" className={styles.section}>
        <h2 id="h-proj">Tes projets</h2>
        {projects.length === 0 ? (
          <p className={styles.empty}>
            Aucun projet pour l’instant.
            {user.roles.includes("PO") && (
              <>
                {" "}
                <Link href="/projets/nouveau">Crée le premier</Link>.
              </>
            )}
          </p>
        ) : (
          <div className={styles.projects}>
            {projects.map((p) => (
              <ProjectCard key={p.id} project={p} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function ProjectCard({ project }: { project: ProjectSummary }) {
  const c = project.status_counts;
  const total = TASK_STATUSES.reduce((sum, s) => sum + c[s], 0);

  return (
    <Link href={`/projets/${project.id}`} className={styles.project}>
      <span className={styles.projectName}>{project.name}</span>
      {project.description && <span className={styles.meta}>{project.description}</span>}
      <span className={styles.bar} aria-hidden>
        {TASK_STATUSES.filter((s) => c[s] > 0).map((s) => (
          <span key={s} style={{ flex: `${c[s]} 1 0`, background: STATUS_COLORS[s] }} />
        ))}
      </span>
      {total === 0 ? (
        <span className={styles.meta}>Aucune tâche</span>
      ) : (
        <ul className={styles.legend} aria-label="Tâches par statut">
          {TASK_STATUSES.filter((s) => c[s] > 0).map((s) => (
            <li key={s}>
              <span className={styles.dot} style={{ background: STATUS_COLORS[s] }} aria-hidden />
              {c[s]} {STATUS_LABELS[s].toLowerCase()}
            </li>
          ))}
        </ul>
      )}
      {project.pending_decisions > 0 && (
        <span>
          <Tag tone="human">
            {project.pending_decisions} à valider
          </Tag>
        </span>
      )}
    </Link>
  );
}

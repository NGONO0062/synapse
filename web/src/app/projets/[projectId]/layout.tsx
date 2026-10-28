import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { AccountMenu, AccountMenuFallback } from "@/components/shell/AccountMenu";
import { NavLink } from "@/components/shell/NavLink";
import shell from "@/components/shell/shell.module.css";
import { STATUS_COLORS } from "@/components/ui/StatusDot";
import { TypeTag } from "@/components/ui/Tag";
import { Logo } from "@/components/ui/Logo";
import { apiFind, apiGet, type Project, type ProjectSummary, type Task } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { STATUS_LABELS, TASK_STATUSES } from "@/lib/domain";
import styles from "./layout.module.css";

// Structure commune des écrans de projet (section 9) : barre latérale des tâches par statut.
export default function ProjectLayout({ children, params }: LayoutProps<"/projets/[projectId]">) {
  return (
    <div className={shell.shell}>
      <aside className={shell.sidebar} aria-label="Tâches du projet">
        <Link href="/" className={shell.brandSmall} aria-label="Synapse, retour à l’accueil">
          <Logo size={22} />
          Synapse
        </Link>
        <Suspense fallback={<div className={shell.nav} />}>
          <ProjectNav params={params} />
        </Suspense>
        <Suspense fallback={<AccountMenuFallback />}>
          <AccountMenu />
        </Suspense>
      </aside>
      <div className={shell.main}>{children}</div>
    </div>
  );
}

async function ProjectNav({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const project = await apiFind<Project>(`/projects/${projectId}`);
  if (!project) notFound();
  const [tasks, projects, user] = await Promise.all([
    apiGet<Task[]>(`/projects/${projectId}/tasks`),
    apiGet<ProjectSummary[]>("/projects"),
    getCurrentUser(),
  ]);
  const isPO = user.roles.includes("PO");
  const others = projects.filter((p) => p.id !== projectId);

  return (
    <>
      <div className={styles.projectBar}>
        <details className={styles.switcher}>
          <summary aria-label={`Projet ${project.name}, changer de projet`}>
            <span>{project.name}</span>
            <svg aria-hidden width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3.5 5.5L7 9l3.5-3.5" />
            </svg>
          </summary>
          <div className={styles.switcherPanel}>
            {others.length === 0 && <span className={shell.empty}>Aucun autre projet.</span>}
            {others.map((p) => (
              <Link key={p.id} href={`/projets/${p.id}`} className={shell.navLink}>
                {p.name}
              </Link>
            ))}
            <Link href="/" className={shell.navLink}>
              Tous les projets
            </Link>
          </div>
        </details>
        <Link
          href={isPO ? `/projets/${projectId}` : `/projets/${projectId}/bugs/nouveau`}
          className={styles.newTask}
          aria-label={isPO ? "Nouvelle tâche" : "Signaler un bug"}
        >
          <svg aria-hidden width="17" height="17" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M8 3v10M3 8h10" />
          </svg>
        </Link>
      </div>

      <nav className={styles.groups} aria-label={isPO ? "Tâches par statut" : "Mes bugs par statut"}>
        {!isPO && <span className={styles.caption}>Mes bugs signalés</span>}
        {TASK_STATUSES.map((status) => {
          const group = tasks.filter((t) => t.status === status);
          return (
            <div key={status} className={styles.group}>
              <span className={shell.navTitle}>
                <span className={styles.dot} style={{ background: STATUS_COLORS[status] }} aria-hidden />
                {STATUS_LABELS[status]}
                <span className={shell.count}>{group.length}</span>
              </span>
              {group.map((task) => (
                <NavLink
                  key={task.id}
                  href={`/projets/${projectId}/taches/${task.code}`}
                  className={`${shell.navLink} ${styles.task}`}
                >
                  <span className={styles.taskTitle}>{task.title}</span>
                  <span className={styles.taskMeta}>
                    <TypeTag type={task.type} small />
                    <code>{task.code}</code>
                    {task.awaiting_human && <span className={styles.awaiting}>en attente</span>}
                    {task.pending_decision === "TESTER_CONFIRMATION" && <span>· à confirmer</span>}
                  </span>
                </NavLink>
              ))}
            </div>
          );
        })}
      </nav>
    </>
  );
}

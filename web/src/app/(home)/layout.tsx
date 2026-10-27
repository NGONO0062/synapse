import Link from "next/link";
import { Suspense } from "react";
import { AccountMenu, AccountMenuFallback } from "@/components/shell/AccountMenu";
import { NavLink } from "@/components/shell/NavLink";
import styles from "@/components/shell/shell.module.css";
import { Logo } from "@/components/ui/Logo";
import { apiGet, type ProjectSummary } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";

// Écrans 2 et 3 : barre latérale avec la liste des projets.
export default function HomeLayout({ children }: LayoutProps<"/">) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Navigation">
        <Link href="/" className={styles.brand}>
          <Logo size={32} />
          Synapse
        </Link>
        <Suspense fallback={<div className={styles.nav} />}>
          <ProjectsNav />
        </Suspense>
        <Suspense fallback={<AccountMenuFallback />}>
          <AccountMenu />
        </Suspense>
      </aside>
      <div className={styles.main}>{children}</div>
    </div>
  );
}

async function ProjectsNav() {
  const [user, projects] = await Promise.all([getCurrentUser(), apiGet<ProjectSummary[]>("/projects")]);
  return (
    <>
      {user.roles.includes("PO") && (
        <NavLink href="/projets/nouveau" className={styles.newProject}>
          <svg aria-hidden width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
            <path d="M8 3v10M3 8h10" />
          </svg>
          Nouveau projet
        </NavLink>
      )}
      <nav className={styles.nav} aria-label="Projets">
        <span className={styles.navTitle}>Projets</span>
        {projects.length === 0 && <span className={styles.empty}>Aucun projet pour l’instant.</span>}
        {projects.map((project) => (
          <NavLink key={project.id} href={`/projets/${project.id}`} className={styles.navLink}>
            <span>{project.name}</span>
            {project.pending_decisions > 0 && (
              <span className={styles.badge}>
                {project.pending_decisions}
                <span className="sr-only"> décision(s) en attente</span>
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </>
  );
}

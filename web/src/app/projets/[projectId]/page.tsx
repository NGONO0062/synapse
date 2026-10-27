import { notFound } from "next/navigation";
import { Suspense } from "react";
import { createTask } from "@/app/actions";
import { Composer } from "@/components/task/Composer";
import { Logo } from "@/components/ui/Logo";
import { apiFind, type Project } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { TASK_TYPES, type TaskType } from "@/lib/domain";
import styles from "./page.module.css";

// Accueil d'un projet : lancer une demande (Feature, Bugfix, Doc).
export default function ProjectPage({ params }: PageProps<"/projets/[projectId]">) {
  return (
    <Suspense fallback={<main className={styles.page} />}>
      <ProjectHome params={params} />
    </Suspense>
  );
}

async function ProjectHome({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  const [project, user] = await Promise.all([apiFind<Project>(`/projects/${projectId}`), getCurrentUser()]);
  if (!project) notFound();
  // Le testeur ne signale que des bugs.
  const types: readonly TaskType[] = user.roles.includes("PO") ? TASK_TYPES : ["BUGFIX"];

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
        <Logo size={56} />
        <h1>{project.name}</h1>
        {project.description && <p className={styles.description}>{project.description}</p>}
        <p className={styles.hint}>
          Décris une demande : l’orchestrateur choisit la casquette, et rien n’avance sans ta validation.
        </p>
      </div>
      <Composer
        action={createTask.bind(null, projectId)}
        field="request"
        label="Nouvelle demande"
        placeholder="Décris une feature, un bugfix ou une doc…"
        taskTypes={types}
        chooseModel
      />
    </main>
  );
}

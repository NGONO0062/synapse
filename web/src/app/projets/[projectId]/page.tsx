import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { createTask } from "@/app/actions";
import { BugForm } from "@/components/task/BugForm";
import { Composer } from "@/components/task/Composer";
import { Logo } from "@/components/ui/Logo";
import { apiFind, apiGet, type Models, type Project } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { TASK_TYPES } from "@/lib/domain";
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
  const [project, user, models] = await Promise.all([
    apiFind<Project>(`/projects/${projectId}`),
    getCurrentUser(),
    apiGet<Models>("/models"),
  ]);
  if (!project) notFound();
  if (!user.roles.includes("PO")) {
    // Le testeur arrive directement sur le signalement (écran 6).
    return (
      <main className={styles.formPage}>
        <h1>Signaler un bug</h1>
        <BugForm projectId={projectId} />
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
        <Logo size={56} />
        <h1>{project.name}</h1>
        {project.description && <p className={styles.description}>{project.description}</p>}
        <p className={styles.hint}>
          Décris une demande : l’orchestrateur choisit la casquette, et rien n’avance sans ta validation.
          Un bugfix décrit ici est reformulé par une casquette, et tu valides la reformulation. Pour un bug
          détaillé, utilise le <Link href={`/projets/${projectId}/bugs/nouveau`}>formulaire de signalement</Link>.
        </p>
      </div>
      <Composer
        action={createTask.bind(null, projectId)}
        field="request"
        label="Nouvelle demande"
        placeholder="Décris une feature, un bugfix ou une doc…"
        taskTypes={TASK_TYPES}
        chooseModel={models.default}
      />
    </main>
  );
}

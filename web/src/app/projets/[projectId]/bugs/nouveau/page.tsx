import type { Metadata } from "next";
import { Suspense } from "react";
import { BugForm } from "@/components/task/BugForm";
import styles from "../../page.module.css";

export const metadata: Metadata = { title: "Signaler un bug · Synapse" };

// Écran 6 · Signaler un bug (testeur ou PO).
export default function NouveauBugPage({ params }: PageProps<"/projets/[projectId]/bugs/nouveau">) {
  return (
    <main className={styles.formPage}>
      <h1>Signaler un bug</h1>
      <Suspense>
        <Form params={params} />
      </Suspense>
    </main>
  );
}

async function Form({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <BugForm projectId={projectId} />;
}

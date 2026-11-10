import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { RunState } from "@/components/usage/RunState";
import styles from "@/components/usage/usage.module.css";
import { apiGet, type EvaluationRun } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { casquetteLabel } from "@/lib/domain";
import { dollars, relativeTime } from "@/lib/format";

// Administrateur (lot 3c) : dernier rejeu des cas de référence de chaque casquette, par modèle.
export default function ReferenceCasesPage() {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <Suspense fallback={<h1>Cas de référence</h1>}>
          <ReferenceCases />
        </Suspense>
      </div>
    </main>
  );
}

async function ReferenceCases() {
  const user = await getCurrentUser();
  if (!user.roles.includes("ADMIN")) notFound();
  const runs = await apiGet<EvaluationRun[]>("/evaluations");
  const regressed = runs.filter((r) => r.regressed_cases.length > 0);

  return (
    <>
      <header className={styles.header}>
        <div>
          <h1>Cas de référence</h1>
          <p className={styles.lead}>
            Chaque casquette rejoue ses cas dès que le modèle réel, ses consignes ou ses cas changent. Seule une
            régression, un cas réussi avant et échoué maintenant, demande ton attention.
          </p>
        </div>
      </header>

      {regressed.length > 0 && (
        <div className={styles.alert} role="alert">
          <strong>
            {regressed.length === 1 ? "Une casquette régresse" : `${regressed.length} casquettes régressent`}
          </strong>
          {regressed.map((r) => `${casquetteLabel(r.casquette)} avec ${r.ai_model}`).join(", ")}. Ouvre le détail pour
          voir les cas concernés avant de garder ce modèle ou ces consignes.
        </div>
      )}

      {runs.length === 0 ? (
        <p className={styles.empty}>
          Aucun rejeu pour l’instant. L’orchestrateur rejoue les cas quand aucune tâche n’attend, si la passerelle
          répond.
        </p>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Casquette</th>
                <th scope="col">Modèle</th>
                <th scope="col">Cas réussis</th>
                <th scope="col">État</th>
                <th scope="col">Rejoué</th>
                <th scope="col">Coût</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.id}>
                  <th scope="row">
                    <Link href={`/admin/cas-de-reference/${run.id}`}>{casquetteLabel(run.casquette)}</Link>
                  </th>
                  <td>{run.ai_model}</td>
                  <td>
                    {run.passed} / {run.total}
                  </td>
                  <td>
                    <RunState run={run} />
                  </td>
                  <td>{relativeTime(run.finished_at ?? run.started_at)}</td>
                  <td>{dollars(run.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

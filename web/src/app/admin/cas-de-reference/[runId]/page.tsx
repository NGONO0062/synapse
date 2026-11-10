import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { RunState } from "@/components/usage/RunState";
import styles from "@/components/usage/usage.module.css";
import { apiFind, type EvaluationResult, type EvaluationRunDetail } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { casquetteLabel } from "@/lib/domain";
import { dayAndTime, dollars } from "@/lib/format";

// Détail d'un rejeu : chaque cas, ce qui n'a pas été tenu, la réponse du modèle, et l'historique.
export default function RunPage({ params }: PageProps<"/admin/cas-de-reference/[runId]">) {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <Suspense fallback={<h1>Cas de référence</h1>}>
          <Run params={params} />
        </Suspense>
      </div>
    </main>
  );
}

async function Run({ params }: { params: Promise<{ runId: string }> }) {
  const [{ runId }, user] = await Promise.all([params, getCurrentUser()]);
  if (!user.roles.includes("ADMIN")) notFound();
  const run = await apiFind<EvaluationRunDetail>(`/evaluations/${runId}`);
  if (!run) notFound();
  const regressed = new Set(run.regressed_cases);
  // Régressions d'abord, puis les autres échecs, puis les cas réussis.
  const rank = (r: EvaluationResult) => (regressed.has(r.case_id) ? 0 : r.passed ? 2 : 1);
  const results = [...run.results].sort((a, b) => rank(a) - rank(b));

  return (
    <>
      <header className={styles.header}>
        <div>
          <p className={styles.lead}>
            <Link href="/admin/cas-de-reference">← Cas de référence</Link>
          </p>
          <h1>
            {casquetteLabel(run.casquette)} · {run.ai_model}
          </h1>
          <p className={styles.lead}>
            {run.passed} cas réussis sur {run.total} · {dayAndTime(run.finished_at ?? run.started_at)} ·{" "}
            {dollars(run.cost_usd)}
          </p>
        </div>
        <RunState run={run} />
      </header>

      <p className={styles.mono}>
        Modèle réel : {run.served_model ?? "inconnu"} · référentiel : {run.referentiel_version}
      </p>

      {run.error && (
        <div className={styles.alert} role="alert">
          <strong>Rejeu interrompu</strong>
          {run.error} L’orchestrateur le reprendra.
        </div>
      )}

      <section className={styles.block}>
        <h2>Cas</h2>
        {results.length === 0 && <p className={styles.empty}>Aucun cas rejoué pour l’instant.</p>}
        <ul className={styles.cases} hidden={results.length === 0}>
          {results.map((result) => (
            <li key={result.case_id}>
              <div className={styles.caseHead}>
                <span className={styles.caseTitle}>{result.title}</span>
                {regressed.has(result.case_id) ? (
                  <span className={`${styles.badge} ${styles.badgeRegression}`}>Régression</span>
                ) : result.passed ? (
                  <span className={`${styles.badge} ${styles.badgeOk}`}>Réussi</span>
                ) : (
                  <span className={`${styles.badge} ${styles.badgeNeutral}`}>Échoué</span>
                )}
                <code className={styles.mono}>{result.case_id}</code>
              </div>
              {result.failures.length > 0 && (
                <ul className={styles.failures}>
                  {result.failures.map((failure) => (
                    <li key={failure}>{failure}</li>
                  ))}
                </ul>
              )}
              {result.answer && (
                <details className={styles.answer}>
                  <summary>Réponse du modèle</summary>
                  <pre>{JSON.stringify(result.answer, null, 2)}</pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      </section>

      {run.history.length > 0 && (
        <section className={styles.block}>
          <h2>Rejeux précédents</h2>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Modèle réel</th>
                  <th scope="col">Cas réussis</th>
                  <th scope="col">État</th>
                </tr>
              </thead>
              <tbody>
                {run.history.map((h) => (
                  <tr key={h.id}>
                    <th scope="row">
                      <Link href={`/admin/cas-de-reference/${h.id}`}>{dayAndTime(h.finished_at ?? h.started_at)}</Link>
                    </th>
                    <td>{h.served_model ?? "inconnu"}</td>
                    <td>
                      {h.passed} / {h.total}
                    </td>
                    <td>
                      <RunState run={h} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

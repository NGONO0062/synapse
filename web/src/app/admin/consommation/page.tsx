import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { MonthNav, UsageTable } from "@/components/usage/Usage";
import styles from "@/components/usage/usage.module.css";
import { apiGet, type WorkspaceUsage } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import { currentMonth, dollars, monthLabel, monthParam } from "@/lib/format";
import { BudgetForm } from "./BudgetForm";

// Administrateur (lot 3c) : consommation de l'espace par projet et par modèle, quotas mensuels.
export default function WorkspaceUsagePage({ searchParams }: PageProps<"/admin/consommation">) {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <Suspense fallback={<h1>Consommation et quotas</h1>}>
          <WorkspaceUsageView searchParams={searchParams} />
        </Suspense>
      </div>
    </main>
  );
}

async function WorkspaceUsageView({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const [user, query] = await Promise.all([getCurrentUser(), searchParams]);
  if (!user.roles.includes("ADMIN")) notFound();
  const month = monthParam(query.mois);
  const usage = await apiGet<WorkspaceUsage>(`/usage${month ? `?month=${month}` : ""}`);
  const current = currentMonth();
  const isCurrent = usage.month === current;
  const fallback = usage.default_budget_usd === null ? "aucun" : dollars(usage.default_budget_usd);

  return (
    <>
      <header className={styles.header}>
        <div>
          <h1>Consommation et quotas</h1>
          <p className={styles.lead}>Appels des casquettes aux modèles IA en {monthLabel(usage.month)}, au prix de la passerelle.</p>
        </div>
        <MonthNav month={usage.month} current={current} href={(m) => `/admin/consommation${m === current ? "" : `?mois=${m}`}`} />
      </header>

      <section className={styles.total} aria-label="Total du mois">
        <span className={styles.totalAmount}>{dollars(usage.cost_usd)}</span>
        <p className={styles.muted}>
          Dont {dollars(usage.evaluations.cost_usd)} pour rejouer les{" "}
          <Link href="/admin/cas-de-reference">cas de référence</Link> ({usage.evaluations.calls} appels).
        </p>
      </section>

      <section className={styles.block}>
        <h2>Par projet</h2>
        {usage.projects.length === 0 ? (
          <p className={styles.empty}>Aucun projet dans l’espace.</p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Projet</th>
                  <th scope="col">Appels</th>
                  <th scope="col">Coût</th>
                  <th scope="col">{isCurrent ? "Quota mensuel ($)" : "Quota actuel"}</th>
                </tr>
              </thead>
              <tbody>
                {usage.projects.map((p) => (
                  <tr key={p.project_id}>
                    <th scope="row">{p.project_name}</th>
                    <td>{p.calls}</td>
                    <td>
                      {dollars(p.cost_usd)}
                      {isCurrent && p.budget_usd !== null && p.cost_usd >= p.budget_usd && (
                        <span className={styles.unpriced}> · quota atteint</span>
                      )}
                    </td>
                    <td>
                      <BudgetForm
                        projectId={p.project_id}
                        projectName={p.project_name}
                        budget={p.budget_is_default ? null : p.budget_usd}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className={styles.note}>
          Quota par défaut de l’espace : {fallback} (réglage <code>SYNAPSE_PROJECT_MONTHLY_BUDGET_USD</code>). Un
          projet qui atteint son quota s’arrête jusqu’au mois suivant, ou jusqu’à ce que tu le relèves.
        </p>
      </section>

      <UsageTable caption="Par modèle" head="Modèle" lines={usage.by_model} />
    </>
  );
}

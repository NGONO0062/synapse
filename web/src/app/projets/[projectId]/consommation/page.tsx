import { notFound } from "next/navigation";
import { Suspense } from "react";
import { MonthNav, QuotaMeter, UsageTable } from "@/components/usage/Usage";
import styles from "@/components/usage/usage.module.css";
import { apiFind, type ProjectUsage } from "@/lib/api";
import { casquetteLabel } from "@/lib/domain";
import { currentMonth, dollars, monthLabel, monthParam } from "@/lib/format";

// Consommation IA du projet (lot 3c) : coût du mois par modèle et par casquette, et quota.
export default function ProjectUsagePage({ params, searchParams }: PageProps<"/projets/[projectId]/consommation">) {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <Suspense fallback={<h1>Consommation IA</h1>}>
          <ProjectUsageView params={params} searchParams={searchParams} />
        </Suspense>
      </div>
    </main>
  );
}

async function ProjectUsageView({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ projectId }, query] = await Promise.all([params, searchParams]);
  const month = monthParam(query.mois);
  const usage = await apiFind<ProjectUsage>(`/projects/${projectId}/usage${month ? `?month=${month}` : ""}`);
  if (!usage) notFound();
  const current = currentMonth();
  const isCurrent = usage.month === current;

  return (
    <>
      <header className={styles.header}>
        <div>
          <h1>Consommation IA</h1>
          <p className={styles.lead}>
            {usage.project_name} · ce que les casquettes ont coûté en {monthLabel(usage.month)}, au prix de la passerelle.
          </p>
        </div>
        <MonthNav
          month={usage.month}
          current={current}
          href={(m) => `/projets/${projectId}/consommation${m === current ? "" : `?mois=${m}`}`}
        />
      </header>

      <section className={styles.total} aria-label="Total du mois">
        <span className={styles.totalAmount}>{dollars(usage.cost_usd)}</span>
        {isCurrent ? (
          <QuotaMeter cost={usage.cost_usd} budget={usage.budget_usd} isDefault={usage.budget_is_default} />
        ) : (
          <p className={styles.muted}>Mois terminé.</p>
        )}
        {isCurrent && usage.budget_usd !== null && (
          <p className={styles.note}>Le quota repart à zéro le 1er du mois. Seul l’administrateur peut le changer.</p>
        )}
      </section>

      <UsageTable caption="Par modèle" head="Modèle" lines={usage.by_model} />
      <UsageTable
        caption="Par casquette"
        head="Casquette"
        lines={usage.by_casquette}
        label={casquetteLabel}
        explainUnpriced={false}
      />
    </>
  );
}

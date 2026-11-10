import Link from "next/link";
import type { UsageLine } from "@/lib/api";
import { dollars, monthLabel, shiftMonth, tokens } from "@/lib/format";
import styles from "./usage.module.css";

// Consommation des modèles IA (lot 3c) : jauge du quota, tableaux par modèle, casquette ou projet.

/** Part du quota consommée : attention à 80 %, atteint à 100 % (les appels s'arrêtent). */
export function QuotaMeter({ cost, budget, isDefault }: { cost: number; budget: number | null; isDefault: boolean }) {
  if (budget === null) {
    return <p className={styles.quotaNone}>Pas de quota : la consommation n’est pas plafonnée.</p>;
  }
  const ratio = budget > 0 ? cost / budget : 1;
  const level = ratio >= 1 ? styles.over : ratio >= 0.8 ? styles.near : styles.ok;
  const percent = Math.min(100, Math.round(ratio * 100));
  return (
    <div className={styles.quota}>
      <div className={styles.quotaText}>
        <span>
          {dollars(cost)} sur {dollars(budget)}
          {isDefault && <span className={styles.muted}> · quota par défaut de l’espace</span>}
        </span>
        <span className={`${styles.quotaState} ${level}`}>
          {ratio >= 1 ? "Quota atteint : les casquettes sont arrêtées" : `${percent} %`}
        </span>
      </div>
      <div
        className={styles.meter}
        role="meter"
        aria-label="Part du quota consommée"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span className={`${styles.meterFill} ${level}`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}

export function UsageTable({
  caption,
  head,
  lines,
  label = (key) => key,
  explainUnpriced = true,
}: {
  caption: string;
  head: string;
  lines: UsageLine[];
  label?: (key: string) => string;
  explainUnpriced?: boolean; // une seule explication par page
}) {
  if (lines.length === 0) {
    return (
      <section className={styles.block}>
        <h2>{caption}</h2>
        <p className={styles.empty}>Aucun appel ce mois-ci.</p>
      </section>
    );
  }
  return (
    <section className={styles.block}>
      <h2>{caption}</h2>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th scope="col">{head}</th>
              <th scope="col">Appels</th>
              <th scope="col">Jetons lus</th>
              <th scope="col">Jetons écrits</th>
              <th scope="col">Coût</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.key}>
                <th scope="row">{label(line.key)}</th>
                <td>{line.calls}</td>
                <td>{tokens(line.input_tokens)}</td>
                <td>{tokens(line.output_tokens)}</td>
                <td>
                  {dollars(line.cost_usd)}
                  {line.unpriced_calls > 0 && (
                    <span className={styles.unpriced}>
                      {" "}
                      · {line.unpriced_calls} sans prix
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {explainUnpriced && lines.some((line) => line.unpriced_calls > 0) && (
        <p className={styles.note}>
          « Sans prix » : la passerelle ne connaît pas le tarif de ce modèle (modèle local, par exemple). Ces appels
          ne comptent pas dans le quota.
        </p>
      )}
    </section>
  );
}

/** Mois affiché, avec le mois précédent et le suivant (jamais au-delà du mois en cours). */
export function MonthNav({ month, current, href }: { month: string; current: string; href: (month: string) => string }) {
  const next = shiftMonth(month, 1);
  return (
    <nav className={styles.months} aria-label="Mois affiché">
      <Link href={href(shiftMonth(month, -1))} aria-label="Mois précédent">
        ←
      </Link>
      <span aria-current="date">{monthLabel(month)}</span>
      {month < current ? (
        <Link href={href(next)} aria-label="Mois suivant">
          →
        </Link>
      ) : (
        <span className={styles.disabled} aria-hidden>
          →
        </span>
      )}
    </nav>
  );
}

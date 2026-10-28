import type { ReactNode } from "react";
import type { Proposal, ReformulatedReport } from "@/lib/api";
import { ENVIRONMENT_LABELS, SEVERITY_LABELS } from "@/lib/domain";
import { relativeTime } from "@/lib/format";
import styles from "./ProposalCard.module.css";

type Props = {
  title: string;
  createdAt: string;
  proposal: Proposal | null;
  footer?: ReactNode; // boutons de décision ou état de la proposition
};

// Carte de proposition (reformulation d'un bug, plan ou résultat). Elle montre aussi ce dont l'agent n'est pas sûr,
// ce qu'il a supposé et ce qu'il n'a pas pu vérifier (dossier, section 1).
export function ProposalCard({ title, createdAt, proposal, footer }: Props) {
  const p = proposal;
  return (
    <article className={styles.card} aria-label={title}>
      <header className={styles.header}>
        <strong>{title}</strong>
        <span className={styles.time}>{relativeTime(createdAt)}</span>
      </header>
      {p && (
        <div className={styles.body}>
          {p.report && <ReportFields report={p.report} />}
          {p.changes.length > 0 && (
            <Section label="Ce qui change">
              {p.changes.map((c) => (
                <span key={c}>{c}</span>
              ))}
            </Section>
          )}
          {p.warnings.map((w) => (
            <p key={w} className={styles.warning}>
              <svg aria-hidden width="16" height="16" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                <path d="M9 2.5L16 15H2L9 2.5z" />
                <path d="M9 7.5v3.5M9 13v.01" />
              </svg>
              {w}
            </p>
          ))}
          <Doubts label="Pas sûr" items={p.uncertainties} />
          <Doubts label="Supposé" items={p.assumptions} />
          <Doubts label="Non vérifié" items={p.unverified} />
          {p.tests && <p className={styles.meta}>{p.tests}</p>}
        </div>
      )}
      {footer && <footer className={styles.footer}>{footer}</footer>}
    </article>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.section}>
      <span className={styles.label}>{label}</span>
      {children}
    </div>
  );
}

function Doubts({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <Section label={label}>
      {items.map((item) => (
        <span key={item} className={styles.doubt}>
          {item}
        </span>
      ))}
    </Section>
  );
}

function ReportFields({ report }: { report: ReformulatedReport }) {
  const rows = [
    ["Titre", report.title],
    ["Environnement", ENVIRONMENT_LABELS[report.environment]],
    ["Navigateur / appareil", report.device || "Non précisé"],
    ["Gravité", SEVERITY_LABELS[report.severity]],
    ["Étapes pour reproduire", report.steps],
    ["Résultat attendu", report.expected],
    ["Résultat obtenu", report.actual],
  ];
  return (
    <dl className={styles.report}>
      {rows.map(([label, value]) => (
        <div key={label} className={styles.section}>
          <dt className={styles.label}>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

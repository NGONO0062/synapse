import Link from "next/link";
import type { ReactNode } from "react";
import type { FileChange, Proposal, Task } from "@/lib/api";
import styles from "./Deliverable.module.css";

// Livrable d'un résultat (écran 5) : lien dans le fil, panneau droit avec diff et tests.

export function hasDeliverable(payload: Proposal | null): payload is Proposal {
  return Boolean(payload && (payload.files.length > 0 || payload.checks.length > 0));
}

export function deliverableTitle(task: Task): string {
  const kind = task.type === "BUGFIX" ? "Correctif" : task.type === "DOC" ? "Documentation" : "Livrable";
  return `${kind} ${task.code}`;
}

function summary(payload: Proposal): string {
  const files = payload.files.length;
  const passing = payload.checks.filter((c) => c.ok).length;
  return [
    files > 0 && `${files} fichier${files > 1 ? "s" : ""}`,
    payload.checks.length > 0 && `${passing}/${payload.checks.length} contrôles au vert`,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function DeliverableLink({ task, payload, href }: { task: Task; payload: Proposal; href: string }) {
  return (
    <Link href={href} scroll={false} className={styles.link}>
      <span className={styles.icon} aria-hidden>
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
          <path d="M5.5 4.5L2 8l3.5 3.5M10.5 4.5L14 8l-3.5 3.5" />
        </svg>
      </span>
      <span className={styles.linkText}>
        <span className={styles.linkTitle}>{deliverableTitle(task)}</span>
        <span className={styles.muted}>{summary(payload)}</span>
      </span>
    </Link>
  );
}

export function DeliverablePanel({
  task,
  payload,
  closeHref,
  footer,
}: {
  task: Task;
  payload: Proposal;
  closeHref: string;
  footer: ReactNode;
}) {
  const title = deliverableTitle(task);
  return (
    <aside className={styles.panel} aria-label={title}>
      <header className={styles.panelHeader}>
        <strong>{title}</strong>
        <Link href={closeHref} scroll={false} className={styles.close} aria-label="Fermer le panneau">
          <svg aria-hidden width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </Link>
      </header>

      <div className={styles.panelBody}>
        {payload.files.map((file) => (
          <FileDiff key={file.path} file={file} />
        ))}

        {payload.checks.length > 0 && (
          <dl className={styles.checks}>
            {payload.checks.map((check) => (
              <div key={check.label}>
                <dt>{check.label}</dt>
                <dd className={check.ok ? styles.ok : styles.ko}>{check.value}</dd>
              </div>
            ))}
          </dl>
        )}

        {payload.note && <p className={styles.muted}>{payload.note}</p>}
      </div>

      {footer && <footer className={styles.panelFooter}>{footer}</footer>}
    </aside>
  );
}

function FileDiff({ file }: { file: FileChange }) {
  return (
    <section className={styles.file} aria-label={file.path}>
      <div className={styles.fileHeader}>
        <code>{file.path}</code>
        <span>
          <span className={styles.ok}>+{file.additions}</span> <span className={styles.ko}>−{file.deletions}</span>
        </span>
      </div>
      {file.diff.length > 0 && (
        <pre className={styles.diff}>
          {file.diff.map((line, i) => {
            const kind = line.startsWith("+") ? styles.added : line.startsWith("-") ? styles.removed : styles.context;
            return (
              <span key={i} className={kind}>
                {line.startsWith("-") ? `−${line.slice(1)}` : line}
              </span>
            );
          })}
        </pre>
      )}
      {file.note && <p className={styles.muted}>{file.note}</p>}
    </section>
  );
}

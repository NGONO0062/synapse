import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ProjectTabs } from "@/components/shell/ProjectTabs";
import { Tag, type TagTone } from "@/components/ui/Tag";
import {
  apiFind,
  MEMORY_DOCUMENTS,
  type ArchitectureSection,
  type E2ETest,
  type MemoryCard,
  type MemoryDecision,
  type MemoryDocument,
  type MemoryDocumentDetail,
  type PlatformStatus,
  type ProjectMemory,
  type Requirement,
  type Scenario,
  type Screen,
} from "@/lib/api";
import { casquetteLabel } from "@/lib/domain";
import styles from "./page.module.css";

// Mémoire du projet (écran 7, lot 4a) : six documents validés, leur historique, l’export Excel.
export default function MemoryPage({ params, searchParams }: PageProps<"/projets/[projectId]/memoire">) {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <Suspense fallback={<h1 className={styles.title}>Mémoire du projet</h1>}>
          <MemoryView params={params} searchParams={searchParams} />
        </Suspense>
      </div>
    </main>
  );
}

const longDate = new Intl.DateTimeFormat("fr", { day: "numeric", month: "short", year: "numeric" });
const date = (iso: string) => longDate.format(new Date(iso));

function chosen(value: string | string[] | undefined, memory: ProjectMemory): MemoryDocument {
  const asked = typeof value === "string" ? value.toUpperCase() : "";
  if ((MEMORY_DOCUMENTS as readonly string[]).includes(asked)) return asked as MemoryDocument;
  return memory.documents.find((d) => d.latest)?.document ?? "EXIGENCES";
}

async function MemoryView({
  params,
  searchParams,
}: {
  params: Promise<{ projectId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const [{ projectId }, query] = await Promise.all([params, searchParams]);
  const memory = await apiFind<ProjectMemory>(`/projects/${projectId}/memory`);
  if (!memory) notFound();
  const selected = chosen(query.document, memory);
  const version = typeof query.version === "string" && /^\d+$/.test(query.version) ? query.version : null;
  const detail = await apiFind<MemoryDocumentDetail>(
    `/projects/${projectId}/memory/${selected}${version ? `?version=${version}` : ""}`,
  );
  if (!detail) notFound();
  const base = `/projets/${projectId}/memoire`;

  return (
    <>
      <ProjectTabs projectId={projectId} current="memoire" />
      <header className={styles.header}>
        <h1 className={styles.title}>Mémoire du projet</h1>
        <code className={styles.path}>{detail.file}</code>
      </header>
      <p className={styles.lead}>
        Tout ce que tu as validé : relu par les casquettes avant chaque tâche, et versionné dans le dépôt du projet, à
        côté du code.
      </p>

      <nav aria-label="Documents de la mémoire" className={styles.cards}>
        {memory.documents.map((card) => (
          <DocumentCard key={card.document} card={card} href={`${base}?document=${card.document}`} current={card.document === selected} />
        ))}
      </nav>

      <section aria-labelledby="document-title" className={styles.document}>
        <div className={styles.documentHead}>
          <h2 id="document-title">
            {detail.label}
            {detail.version && ` · version ${detail.version.version}`}
          </h2>
          {selected === "SCENARIOS" && detail.latest && (
            <a href={`${base}/scenarios.xlsx`} className={styles.download} download>
              <svg aria-hidden width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M8 2v9M4.5 7.5L8 11l3.5-3.5M3 14h10" />
              </svg>
              Télécharger l’Excel
            </a>
          )}
        </div>
        {detail.version ? (
          <>
            <p className={styles.meta}>
              Validée le {date(detail.version.validated_at)} par {detail.version.validated_by}
              {detail.version.source_task && (
                <>
                  {" "}
                  avec <Link href={`/projets/${projectId}/taches/${detail.version.source_task}`}>{detail.version.source_task}</Link>
                </>
              )}
              {" · "}
              {detail.version.commit ? (
                <>
                  écrite dans le dépôt (<code>{detail.version.commit.slice(0, 8)}</code>)
                </>
              ) : (
                "écriture dans le dépôt en cours"
              )}
              {detail.latest && detail.version.version !== detail.latest.version && (
                <>
                  {" · "}
                  <Link href={`${base}?document=${selected}`}>voir la dernière version</Link>
                </>
              )}
            </p>
            <DocumentItems document={selected} items={detail.items} />
          </>
        ) : (
          <p className={styles.empty}>{EMPTY[selected]}</p>
        )}
      </section>

      {detail.history.length > 0 && (
        <section aria-labelledby="history-title" className={styles.history}>
          <h2 id="history-title">Historique</h2>
          <ol>
            {detail.history.map((v) => (
              <li key={v.version}>
                <Link
                  href={`${base}?document=${selected}&version=${v.version}`}
                  aria-current={detail.version?.version === v.version ? "page" : undefined}
                >
                  v{v.version}
                </Link>
                <span>{v.summary}</span>
                <span className={styles.muted}>
                  {date(v.validated_at)} · {v.validated_by}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}

const EMPTY: Record<MemoryDocument, string> = {
  EXIGENCES: "Aucune exigence validée. Le Business Analyst en propose avec le livrable de chaque Feature ; elles entrent ici quand tu valides le résultat.",
  MAQUETTES: "Aucun écran validé. Les maquettes arriveront avec la création d’un projet de zéro.",
  ARCHITECTURE: "Aucune décision d’architecture validée. Elle arrivera avec la création d’un projet de zéro.",
  SCENARIOS: "Aucun scénario validé. L’Analyste de test en écrit à partir des exigences, avec le livrable de chaque Feature ou Bugfix.",
  TESTS_E2E: "Aucun parcours critique automatisé pour l’instant.",
  DECISIONS: "Aucune décision. Chaque réponse que tu donnes à une casquette s’ajoute ici, datée.",
};

function DocumentCard({ card, href, current }: { card: MemoryCard; href: string; current: boolean }) {
  return (
    <Link href={href} className={styles.card} aria-current={current ? "page" : undefined}>
      <span className={styles.cardTitle}>{card.label}</span>
      <span className={styles.muted}>{card.latest ? `v${card.latest.version} · ${card.count_label}` : "Rien de validé"}</span>
      {card.latest && (
        <Tag tone="human" small>
          Validé
        </Tag>
      )}
    </Link>
  );
}

function DocumentItems({ document, items }: { document: MemoryDocument; items: Record<string, unknown>[] }) {
  if (items.length === 0) return <p className={styles.empty}>Document vide à cette version.</p>;
  switch (document) {
    case "EXIGENCES":
      return <Requirements items={items as Requirement[]} />;
    case "SCENARIOS":
      return <Scenarios items={items as Scenario[]} />;
    case "DECISIONS":
      return <Decisions items={items as MemoryDecision[]} />;
    case "MAQUETTES":
      return (
        <ul className={styles.list}>
          {(items as Screen[]).map((s) => (
            <li key={s.name}>
              <strong>{s.name}</strong>
              {s.journey && <span className={styles.muted}>Parcours : {s.journey}</span>}
              {s.description && <p>{s.description}</p>}
            </li>
          ))}
        </ul>
      );
    case "ARCHITECTURE":
      return (
        <ul className={styles.list}>
          {(items as ArchitectureSection[]).map((s) => (
            <li key={s.title}>
              <strong>{s.title}</strong>
              {s.body && <p className={styles.prose}>{s.body}</p>}
            </li>
          ))}
        </ul>
      );
    case "TESTS_E2E":
      return (
        <ul className={styles.list}>
          {(items as E2ETest[]).map((t) => (
            <li key={t.journey}>
              <strong>{t.journey}</strong>
              {t.justification && <p>{t.justification}</p>}
              {t.file && <code className={styles.muted}>{t.file}</code>}
            </li>
          ))}
        </ul>
      );
  }
}

function Requirements({ items }: { items: Requirement[] }) {
  return (
    <ul className={styles.list}>
      {items.map((r) => (
        <li key={r.id}>
          <span className={styles.itemHead}>
            <code>{r.id}</code>
            <strong>{r.title}</strong>
            <span className={styles.muted}>{r.module}</span>
          </span>
          <p>{r.statement}</p>
          <ul className={styles.criteria} aria-label={`Critères d’acceptation de ${r.id}`}>
            {r.acceptance.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

const STATUS_TONES: Record<PlatformStatus, TagTone> = { Passed: "human", Failed: "error", "Not started": "neutral" };
const PLATFORMS = [
  ["chrome", "Chrome"],
  ["firefox", "Firefox"],
  ["ios", "iOS"],
  ["android", "Android"],
] as const;

function Scenarios({ items }: { items: Scenario[] }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Module</th>
            <th scope="col">Scénario</th>
            <th scope="col">Préconditions</th>
            <th scope="col">Étapes</th>
            <th scope="col">Résultat attendu</th>
            {PLATFORMS.map(([, label]) => (
              <th key={label} scope="col" className={styles.center}>
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.id}>
              <th scope="row">{s.module}</th>
              <td>
                {s.scenario}
                <span className={styles.refs}>
                  <code>{s.id}</code>
                  {s.requirements.length > 0 && ` · ${s.requirements.join(", ")}`}
                </span>
              </td>
              <td className={styles.soft}>{s.preconditions || "—"}</td>
              <td className={`${styles.soft} ${styles.steps}`}>{s.steps}</td>
              <td className={styles.soft}>{s.expected}</td>
              {PLATFORMS.map(([key, label]) => (
                <td key={key} className={styles.center}>
                  <Tag tone={STATUS_TONES[s[key]]} small>
                    <span className="sr-only">{label} : </span>
                    {s[key]}
                  </Tag>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Decisions({ items }: { items: MemoryDecision[] }) {
  return (
    <ol className={styles.list}>
      {[...items].reverse().map((d, i) => (
        <li key={`${d.date}-${i}`}>
          <span className={styles.itemHead}>
            <strong>{date(d.date)}</strong>
            <span className={styles.muted}>
              {d.author}
              {d.task && ` · ${d.task}`}
            </span>
          </span>
          <p className={styles.soft}>
            {d.casquette ? `${casquetteLabel(d.casquette)} : ` : "Question : "}
            {d.question}
          </p>
          <p>Réponse : {d.answer}</p>
        </li>
      ))}
    </ol>
  );
}

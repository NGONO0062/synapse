import type { Metadata } from "next";
import { Button } from "@/components/ui/Button";
import { CasquetteChain } from "@/components/ui/CasquetteChain";
import { Logo } from "@/components/ui/Logo";
import { StatusDot } from "@/components/ui/StatusDot";
import { TypeTag } from "@/components/ui/Tag";
import { TASK_STATUSES, TASK_TYPES } from "@/lib/domain";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Design system · Synapse" };

const SWATCHES = [
  { name: "Barre latérale", token: "--sy-sidebar", value: "#0A0B0D" },
  { name: "Fond", token: "--sy-bg", value: "#101114" },
  { name: "Surface", token: "--sy-surface", value: "#17181C" },
  { name: "Texte", token: "--sy-text", value: "#F2F3F5" },
  { name: "IA", token: "--sy-ai", value: "#8E9BFF / #2A2E52" },
  { name: "Humain", token: "--sy-human", value: "#3FBF9A / #173A30" },
];

// Écran 0 · Design system
export default function DesignSystemPage() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={`${styles.card} ${styles.logoCard}`}>
          <div className={styles.brand}>
            <Logo size={48} />
            <span className={styles.wordmark}>Synapse</span>
          </div>
          <div className={styles.logoVariants}>
            <span className={styles.logoOnLight}>
              <Logo size={36} onLight />
            </span>
            <span className={styles.logoOnSidebar}>
              <Logo size={36} />
            </span>
            <span className={styles.logoOnAi}>
              <Logo size={36} />
            </span>
          </div>
        </div>
        <div className={styles.intro}>
          <h1>Un centre, des branches.</h1>
          <p>
            Le logo montre un noyau relié à des nœuds. Dans l’app, le noyau c’est l’orchestrateur, et chaque
            branche une casquette de l’équipe. On retrouve cette idée partout : des nœuds ronds reliés par un
            trait pour montrer le cheminement, des boutons en pilule, des coins généreux, et seulement deux
            couleurs qui portent du sens.
          </p>
          <CasquetteChain
            steps={[
              { casquette: "BUSINESS_ANALYST", state: "done" },
              { casquette: "ARCHITECTE", state: "active" },
              { casquette: "DEVELOPPEUR", state: "pending" },
              { casquette: "ANALYSTE_TEST", label: "QA", state: "pending" },
            ]}
          />
        </div>
      </section>

      <div className={styles.grid}>
        <section aria-labelledby="ds-couleurs">
          <h2 id="ds-couleurs" className={styles.eyebrow}>
            Couleurs
          </h2>
          <ul className={styles.swatches}>
            {SWATCHES.map((s) => (
              <li key={s.token}>
                <span className={styles.swatch} style={{ background: `var(${s.token})` }} aria-hidden />
                <strong>{s.name}</strong>
                <code>{s.value}</code>
              </li>
            ))}
          </ul>
          <p className={styles.note}>
            Le logo reste blanc sur sombre. L’indigo marque ce que fait l’IA, le vert ce que décide un humain.
          </p>
        </section>

        <section aria-labelledby="ds-typo">
          <h2 id="ds-typo" className={styles.eyebrow}>
            Typographie
          </h2>
          <div className={`${styles.card} ${styles.typo}`}>
            <p className={styles.display}>Que construit-on ?</p>
            <p className={styles.caption}>Sora · titres, géométrique et rond comme le logo</p>
            <p className={styles.body}>Voici le plan. Rien ne sera codé tant que tu ne l’as pas validé.</p>
            <p className={styles.caption}>Manrope · texte, interface et réponses de l’agent</p>
            <code className={styles.mono}>GET /timesheets/&#123;id&#125;/export · FEAT-019</code>
            <p className={styles.caption}>IBM Plex Mono · code et identifiants</p>
          </div>
        </section>

        <section aria-labelledby="ds-statuts">
          <h2 id="ds-statuts" className={styles.eyebrow}>
            Statuts et types
          </h2>
          <ul className={styles.statuses}>
            {TASK_STATUSES.map((status) => (
              <li key={status}>
                <StatusDot status={status} withLabel />
              </li>
            ))}
          </ul>
          <div className={styles.tags}>
            {TASK_TYPES.map((type) => (
              <TypeTag key={type} type={type} />
            ))}
          </div>
        </section>

        <section aria-labelledby="ds-boutons">
          <h2 id="ds-boutons" className={styles.eyebrow}>
            Boutons
          </h2>
          <div className={styles.buttons}>
            <Button variant="human">Valider</Button>
            <Button variant="primary">Lancer</Button>
            <Button variant="outline">Modifier</Button>
          </div>
          <p className={styles.note}>Le vert est réservé aux décisions humaines. L’IA n’a jamais de bouton vert.</p>
        </section>

        <section aria-labelledby="ds-saisie">
          <h2 id="ds-saisie" className={styles.eyebrow}>
            Barre de saisie
          </h2>
          <div className={styles.composer}>
            <label htmlFor="ds-composer" className="sr-only">
              Message
            </label>
            <input id="ds-composer" placeholder="Décris une feature, un bugfix…" />
            <button type="button" className={styles.send} aria-label="Envoyer">
              ↑
            </button>
          </div>
          <p className={styles.note}>+ · micro · type de tâche · modèle IA · Validation manuelle</p>
        </section>

        <section aria-labelledby="ds-proposition">
          <h2 id="ds-proposition" className={styles.eyebrow}>
            Carte de proposition
          </h2>
          <article className={`${styles.card} ${styles.proposal}`}>
            <header>
              <strong>Plan · version 2</strong>
              <a href="#">Ouvrir</a>
            </header>
            <p className={styles.note}>Ce qui change · impact · tests prévus · questions</p>
            <div className={styles.buttons}>
              <Button variant="human">Valider le plan</Button>
              <Button variant="outline">Modifier</Button>
            </div>
          </article>
        </section>
      </div>
    </main>
  );
}

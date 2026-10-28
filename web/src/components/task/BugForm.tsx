"use client";

import { useActionState, useState } from "react";
import { reportBug, reportBugInWords } from "@/app/actions";
import { Button } from "@/components/ui/Button";
import { SEVERITY_LABELS } from "@/lib/domain";
import styles from "./BugForm.module.css";

type Mode = "words" | "detailed";

// Écran 6 · Signaler un bug : en quelques mots (par défaut) ou par le formulaire détaillé.
export function BugForm({ projectId }: { projectId: string }) {
  const [mode, setMode] = useState<Mode>("words");
  return (
    <>
      <div role="tablist" aria-label="Façon de signaler" className={styles.tabs}>
        <button type="button" role="tab" aria-selected={mode === "words"} onClick={() => setMode("words")}>
          En quelques mots
        </button>
        <button type="button" role="tab" aria-selected={mode === "detailed"} onClick={() => setMode("detailed")}>
          Formulaire détaillé
        </button>
      </div>
      {mode === "words" ? <BugInWordsForm projectId={projectId} /> : <DetailedBugForm projectId={projectId} />}
    </>
  );
}

// Une casquette reformule le texte ; l'auteur valide la reformulation avant la priorisation.
function BugInWordsForm({ projectId }: { projectId: string }) {
  const [state, formAction, pending] = useActionState(reportBugInWords.bind(null, projectId), { error: null });

  return (
    <form action={formAction} className={styles.form} role="tabpanel">
      <div className={styles.field}>
        <label htmlFor="bug-text">Que s’est-il passé ?</label>
        <textarea
          id="bug-text"
          name="text"
          rows={6}
          maxLength={20000}
          placeholder="Ex. : quand je saisis 2 h le samedi, le total de la semaine reste à 40 h au lieu de 42 h. Vu sur Chrome Android, en staging."
          required
        />
        <p className={styles.help}>
          Le Débogueur en tire le titre, les étapes, l’attendu, l’obtenu, l’environnement et la gravité. Tu valides sa
          reformulation avant que le bug parte au PO.
        </p>
      </div>

      {state.error && (
        <p className={styles.error} role="alert">
          {state.error}
        </p>
      )}

      <div className={styles.footer}>
        <Button type="submit" variant="primary" disabled={pending}>
          Envoyer le bug
        </Button>
      </div>
    </form>
  );
}

// Repris de docs/maquettes-html/07-BugTesteur.html.
function DetailedBugForm({ projectId }: { projectId: string }) {
  const [state, formAction, pending] = useActionState(reportBug.bind(null, projectId), { error: null });

  return (
    <form action={formAction} className={styles.form} role="tabpanel">
      <div className={styles.field}>
        <label htmlFor="bug-title">Titre</label>
        <input id="bug-title" name="title" type="text" placeholder="Ex. : le total de la semaine ne compte pas le samedi" maxLength={300} required />
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label htmlFor="bug-env">Environnement</label>
          <select id="bug-env" name="environment" defaultValue="STAGING">
            <option value="STAGING">Staging</option>
            <option value="PREPROD">Préprod</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="bug-device">Navigateur / appareil</label>
          <input id="bug-device" name="device" type="text" placeholder="Ex. : Chrome, Android" maxLength={200} />
        </div>
      </div>

      <div className={styles.field}>
        <label htmlFor="bug-steps">Étapes pour reproduire</label>
        <textarea
          id="bug-steps"
          name="steps"
          rows={4}
          placeholder={"1. Se connecter en tant que collaborateur\n2. Ouvrir la semaine en cours\n3. Saisir 2 h le samedi"}
          required
        />
      </div>

      <div className={styles.row}>
        <div className={styles.field}>
          <label htmlFor="bug-expected">Résultat attendu</label>
          <textarea id="bug-expected" name="expected" rows={2} required />
        </div>
        <div className={styles.field}>
          <label htmlFor="bug-actual">Résultat obtenu</label>
          <textarea id="bug-actual" name="actual" rows={2} required />
        </div>
      </div>

      <fieldset className={styles.severity}>
        <legend>Gravité</legend>
        <div className={styles.choices}>
          {Object.entries(SEVERITY_LABELS).map(([value, label]) => (
            <label key={value} className={styles.choice}>
              <input type="radio" name="severity" value={value} defaultChecked={value === "MAJEUR"} /> {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className={styles.field}>
        <span className={styles.label}>Captures ou vidéo</span>
        <p className={styles.drop}>Le dépôt de captures (PNG, JPG ou MP4) arrive avec le stockage des fichiers.</p>
      </div>

      {state.error && (
        <p className={styles.error} role="alert">
          {state.error}
        </p>
      )}

      <div className={styles.footer}>
        <Button type="submit" variant="primary" disabled={pending}>
          Envoyer le bug
        </Button>
      </div>
    </form>
  );
}

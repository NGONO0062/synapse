"use client";

import { useActionState } from "react";
import { reportBug } from "@/app/actions";
import { Button } from "@/components/ui/Button";
import { SEVERITY_LABELS } from "@/lib/domain";
import styles from "./BugForm.module.css";

// Écran 6 · Signaler un bug (repris de docs/maquettes-html/07-BugTesteur.html).
export function BugForm({ projectId }: { projectId: string }) {
  const [state, formAction, pending] = useActionState(reportBug.bind(null, projectId), { error: null });

  return (
    <form action={formAction} className={styles.form}>
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

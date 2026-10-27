"use client";

import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import styles from "./page.module.css";

// L'authentification passe par Keycloak (OIDC) ; le branchement arrive avec le lot Identité.
const NOT_WIRED = "La connexion n’est pas encore branchée sur Keycloak.";

export function LoginForm() {
  const [notice, setNotice] = useState<string | null>(null);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(NOT_WIRED);
  }

  return (
    <div className={styles.card}>
      <Button variant="outline" block className={styles.sso} onClick={() => setNotice(NOT_WIRED)}>
        <MailIcon />
        Continuer avec le compte de l’entreprise (SSO)
      </Button>

      <div className={styles.divider} role="separator">
        <span>ou</span>
      </div>

      <form className={styles.form} onSubmit={handleSubmit} noValidate>
        <Field
          id="email"
          name="email"
          type="email"
          label="E-mail"
          placeholder="nom@entreprise.com"
          autoComplete="username"
          required
        />
        <Field
          id="password"
          name="password"
          type="password"
          label="Mot de passe"
          autoComplete="current-password"
          required
          aside={
            <a href="#" className={styles.forgot}>
              Mot de passe oublié ?
            </a>
          }
        />
        <Button type="submit" variant="primary" block>
          Se connecter
        </Button>
      </form>

      <p className={styles.notice} role="status" aria-live="polite">
        {notice}
      </p>
    </div>
  );
}

function MailIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden>
      <rect x="2.5" y="3.5" width="13" height="11" rx="2" />
      <path d="M2.5 5l6.5 5 6.5-5" />
    </svg>
  );
}

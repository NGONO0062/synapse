import type { Metadata } from "next";
import { Logo } from "@/components/ui/Logo";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Connexion impossible · Synapse" };

export default function ConnexionErreurPage() {
  return (
    <main className={styles.page}>
      <Logo size={56} />
      <h1>La connexion n’a pas abouti.</h1>
      <p>Le lien de connexion a peut-être expiré. Recommence depuis le début.</p>
      <a className={styles.retry} href="/auth/login">
        Réessayer
      </a>
    </main>
  );
}

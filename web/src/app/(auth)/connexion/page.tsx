import type { Metadata } from "next";
import { Logo } from "@/components/ui/Logo";
import { LoginForm } from "./LoginForm";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Connexion · Synapse" };

// Écran 1 · Connexion
export default function ConnexionPage() {
  return (
    <main className={styles.page}>
      <div className={styles.column}>
        <header className={styles.header}>
          <Logo size={72} />
          <h1 className={styles.title}>Synapse</h1>
          <p className={styles.tagline}>Ton équipe logicielle IA. Elle propose, tu valides.</p>
        </header>
        <LoginForm />
        <p className={styles.footer}>
          Pas encore de compte ? Demande une invitation à l’administrateur de ton espace.
        </p>
      </div>
    </main>
  );
}

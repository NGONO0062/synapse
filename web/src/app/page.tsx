import { Suspense } from "react";
import { AccountCard } from "@/components/AccountCard";
import { Logo } from "@/components/ui/Logo";
import { apiGet, type Me } from "@/lib/api";
import { getCurrentUser } from "@/lib/auth/current-user";
import styles from "./page.module.css";

// Écran 2 · Accueil (début) : le message d'accueil. Décisions en attente et projets : lot 2.
export default function HomePage() {
  return (
    <main className={styles.page}>
      <Logo size={56} />
      <Suspense fallback={<h1 className={styles.greeting}>Bonjour</h1>}>
        <Greeting />
      </Suspense>
    </main>
  );
}

async function Greeting() {
  const [user, me] = await Promise.all([getCurrentUser(), apiGet<Me>("/me")]);
  return (
    <>
      <h1 className={styles.greeting}>Bonjour {user.givenName ?? user.name}</h1>
      <AccountCard user={user} apiRoles={me.roles} />
    </>
  );
}

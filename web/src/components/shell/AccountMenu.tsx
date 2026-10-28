import { getCurrentUser } from "@/lib/auth/current-user";
import { authConfig } from "@/lib/auth/config";
import { ROLE_LABELS } from "@/lib/domain";
import { initials } from "@/lib/format";
import styles from "./AccountMenu.module.css";

// Menu du compte, en bas de la barre latérale. v1 : profil et déconnexion.
export async function AccountMenu() {
  const user = await getCurrentUser();
  const role = user.roles.map((r) => ROLE_LABELS[r]).join(", ") || "Aucun rôle";

  return (
    <details className={styles.menu}>
      <summary className={styles.summary} aria-label={`Mon compte : ${user.name}, ${role}`}>
        <span className={user.roles.includes("PO") ? styles.avatar : `${styles.avatar} ${styles.tester}`} aria-hidden>
          {initials(user.name)}
        </span>
        <span className={styles.identity}>
          <span className={styles.name}>{user.name}</span>
          <span className={styles.meta}>
            {role}
            {user.email ? ` · ${user.email}` : ""}
          </span>
        </span>
        <svg className={styles.chevron} aria-hidden width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 8.5L7 5.5l3 3" />
        </svg>
      </summary>
      <div className={styles.panel}>
        <a className={styles.item} href={`${authConfig.issuer}/account`}>
          Mon profil
        </a>
        <form action="/auth/logout" method="post">
          <button type="submit" className={styles.item}>
            Se déconnecter
          </button>
        </form>
      </div>
    </details>
  );
}

export function AccountMenuFallback() {
  return <div className={styles.fallback} aria-hidden />;
}

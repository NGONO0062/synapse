import { Button } from "@/components/ui/Button";
import type { SessionUser } from "@/lib/auth/session";
import { ROLE_LABELS, type Role } from "@/lib/domain";
import styles from "./AccountCard.module.css";

// Menu du compte (v1 : profil et déconnexion). Rejoindra le bas de la barre latérale au lot 2.
export function AccountCard({ user, apiRoles }: { user: SessionUser; apiRoles: string[] }) {
  const initials = user.name
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
  const roles = apiRoles.filter((r): r is Role => r in ROLE_LABELS).map((r) => ROLE_LABELS[r]);

  return (
    <section className={styles.card} aria-label="Ton compte">
      <span className={styles.avatar} aria-hidden>
        {initials}
      </span>
      <div className={styles.identity}>
        <strong>{user.name}</strong>
        <span>{roles.join(", ") || "Aucun rôle Synapse"}</span>
        {user.email && <span>{user.email}</span>}
      </div>
      <form action="/auth/logout" method="post">
        <Button type="submit" variant="outline">
          Se déconnecter
        </Button>
      </form>
    </section>
  );
}

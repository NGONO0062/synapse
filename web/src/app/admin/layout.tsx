import Link from "next/link";
import { Suspense } from "react";
import { AccountMenu, AccountMenuFallback } from "@/components/shell/AccountMenu";
import { NavLink } from "@/components/shell/NavLink";
import styles from "@/components/shell/shell.module.css";
import { Logo } from "@/components/ui/Logo";

// Espace de l'administrateur (lot 3c) : consommation et quotas, cas de référence des casquettes.
// Il ne montre rien du contenu des projets (dossier, Visibilité).
export default function AdminLayout({ children }: LayoutProps<"/admin">) {
  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar} aria-label="Navigation">
        <Link href="/admin/consommation" className={styles.brand}>
          <Logo size={32} />
          Synapse
        </Link>
        <Suspense fallback={<div className={styles.nav} />}>
          <AdminNav />
        </Suspense>
        <Suspense fallback={<AccountMenuFallback />}>
          <AccountMenu />
        </Suspense>
      </aside>
      <div className={styles.main}>{children}</div>
    </div>
  );
}

// Le lien actif dépend de l'URL : rendu au moment de la requête, derrière <Suspense>.
function AdminNav() {
  return (
    <nav className={styles.nav} aria-label="Administration">
      <span className={styles.navTitle}>Administration</span>
      <NavLink href="/admin/consommation" className={styles.navLink}>
        Consommation et quotas
      </NavLink>
      <NavLink href="/admin/cas-de-reference" className={styles.navLink}>
        Cas de référence
      </NavLink>
    </nav>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

// Lien de navigation qui porte aria-current="page" quand il pointe sur la page affichée.
export function NavLink({ href, className, children }: { href: string; className?: string; children: ReactNode }) {
  const pathname = usePathname();
  return (
    <Link href={href} className={className} aria-current={pathname === href ? "page" : undefined}>
      {children}
    </Link>
  );
}

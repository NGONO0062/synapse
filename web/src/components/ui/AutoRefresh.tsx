"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Recharge les données de la page tant que des casquettes travaillent : l'humain voit
// avancer leur travail sans recharger. L'état local (saisie en cours) est conservé.
export function AutoRefresh({ active, every = 4000 }: { active: boolean; every?: number }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => router.refresh(), every);
    return () => clearInterval(timer);
  }, [active, every, router]);
  return null;
}

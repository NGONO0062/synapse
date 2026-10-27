import "server-only";
import { redirect } from "next/navigation";
import { authConfig } from "./auth/config";
import { getAccessToken } from "./auth/current-user";

// Appels à l'API Synapse depuis le serveur Next, avec le jeton de la session.
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(new URL(path, authConfig.apiUrl), {
    headers: { Authorization: `Bearer ${await getAccessToken()}` },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/connexion");
  if (!response.ok) throw new Error(`API ${path} : ${response.status}`);
  return response.json() as Promise<T>;
}

export type Me = { subject: string; name: string; email: string | null; roles: string[] };

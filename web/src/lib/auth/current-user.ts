import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { readSession, type Session, type SessionUser } from "./session";

// Couche d'accès : seul endroit où les composants serveur lisent la session.
// À appeler derrière une frontière <Suspense> (lecture au moment de la requête).

async function requireSession(): Promise<Session> {
  const session = await readSession(await cookies());
  if (!session) redirect("/connexion");
  return session;
}

export async function getCurrentUser(): Promise<SessionUser> {
  return (await requireSession()).user;
}

export async function getAccessToken(): Promise<string> {
  return (await requireSession()).accessToken;
}

import { NextResponse, type NextRequest } from "next/server";
import { refreshSession } from "@/lib/auth/oidc";
import { SESSION_COOKIE, clearSession, isExpiring, readSession, writeSession } from "@/lib/auth/session";

// Garde des pages de l'application : sans session, retour à la connexion.
// Renouvelle aussi le jeton d'accès avant son expiration, car un composant serveur ne peut
// pas réécrire de cookie. L'autorisation fine reste vérifiée par l'API à chaque appel.
export async function proxy(request: NextRequest) {
  const session = await readSession(request.cookies);
  if (!session) return toLogin(request);
  if (!isExpiring(session)) return NextResponse.next();

  try {
    const refreshed = await refreshSession(session);
    // On réécrit les cookies sur la requête (pour le rendu en cours) et sur la réponse.
    await writeSession(
      {
        set: (name, value) => request.cookies.set(name, value),
        delete: (name) => request.cookies.delete(name),
      },
      refreshed,
    );
    const response = NextResponse.next({ request: { headers: request.headers } });
    await writeSession(response.cookies, refreshed);
    return response;
  } catch {
    return toLogin(request);
  }
}

function toLogin(request: NextRequest) {
  const login = new URL("/auth/login", request.url);
  login.searchParams.set("returnTo", request.nextUrl.pathname + request.nextUrl.search);
  const response = NextResponse.redirect(login);
  if (request.cookies.has(`${SESSION_COOKIE}.0`)) clearSession(response.cookies);
  return response;
}

export const config = {
  // Tout sauf : flux d'authentification, connexion, design system, ressources statiques.
  matcher: ["/((?!auth/|connexion|design-system|_next/static|_next/image|favicon.ico|logo-).*)"],
};

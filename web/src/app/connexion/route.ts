import { NextResponse, type NextRequest } from "next/server";

// Écran 1 · Connexion : servi par Keycloak (thème infra/keycloak/themes/synapse).
export function GET(request: NextRequest) {
  const login = new URL("/auth/login", request.url);
  const returnTo = request.nextUrl.searchParams.get("returnTo");
  if (returnTo) login.searchParams.set("returnTo", returnTo);
  return NextResponse.redirect(login);
}

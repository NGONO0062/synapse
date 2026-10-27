import * as client from "openid-client";
import { NextResponse, type NextRequest } from "next/server";
import { authConfig } from "@/lib/auth/config";
import { oidc } from "@/lib/auth/oidc";
import { clearSession, readSession } from "@/lib/auth/session";

// Déconnexion (POST depuis le menu du compte) : ferme la session locale puis celle de Keycloak.
export async function POST(request: NextRequest) {
  const session = await readSession(request.cookies);
  const afterLogout = new URL("/connexion", authConfig.appUrl).toString();

  let target = afterLogout;
  if (session) {
    target = client
      .buildEndSessionUrl(await oidc(), {
        id_token_hint: session.idToken,
        post_logout_redirect_uri: afterLogout,
      })
      .toString();
  }

  const response = NextResponse.redirect(target, { status: 303 });
  clearSession(response.cookies);
  return response;
}

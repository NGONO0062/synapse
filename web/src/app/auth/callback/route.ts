import * as client from "openid-client";
import { NextResponse, type NextRequest } from "next/server";
import { authConfig } from "@/lib/auth/config";
import { callbackUrl, oidc, safeReturnTo } from "@/lib/auth/oidc";
import { FLOW_COOKIE, sessionFromTokens, unseal, writeSession } from "@/lib/auth/session";

type Flow = { verifier: string; state: string; returnTo: string };

// Retour de Keycloak : échange du code contre les jetons, puis ouverture de la session.
export async function GET(request: NextRequest) {
  const failure = NextResponse.redirect(new URL("/connexion/erreur", authConfig.appUrl));
  failure.cookies.delete(FLOW_COOKIE);

  const sealedFlow = request.cookies.get(FLOW_COOKIE)?.value;
  const flow = sealedFlow ? await unseal<Flow>(sealedFlow) : null;
  if (!flow) return failure;

  // L'URL de retour est reconstruite depuis APP_URL pour correspondre au redirect_uri enregistré.
  const currentUrl = new URL(callbackUrl());
  currentUrl.search = request.nextUrl.search;

  try {
    const tokens = await client.authorizationCodeGrant(await oidc(), currentUrl, {
      pkceCodeVerifier: flow.verifier,
      expectedState: flow.state,
      idTokenExpected: true,
    });
    const response = NextResponse.redirect(new URL(safeReturnTo(flow.returnTo), authConfig.appUrl));
    response.cookies.delete(FLOW_COOKIE);
    await writeSession(response.cookies, sessionFromTokens(tokens));
    return response;
  } catch (error) {
    console.error("Échec de la connexion OIDC", error);
    return failure;
  }
}

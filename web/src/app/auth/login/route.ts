import * as client from "openid-client";
import { NextResponse, type NextRequest } from "next/server";
import { callbackUrl, oidc, safeReturnTo } from "@/lib/auth/oidc";
import { FLOW_COOKIE, flowCookieOptions, seal } from "@/lib/auth/session";

// Démarre la connexion : redirige vers Keycloak (code + PKCE).
export async function GET(request: NextRequest) {
  const config = await oidc();
  const verifier = client.randomPKCECodeVerifier();
  const state = client.randomState();
  const returnTo = safeReturnTo(request.nextUrl.searchParams.get("returnTo"));

  const authorizationUrl = client.buildAuthorizationUrl(config, {
    redirect_uri: callbackUrl(),
    scope: "openid profile email",
    code_challenge: await client.calculatePKCECodeChallenge(verifier),
    code_challenge_method: "S256",
    state,
  });

  const response = NextResponse.redirect(authorizationUrl);
  response.cookies.set(FLOW_COOKIE, await seal({ verifier, state, returnTo }, 600), flowCookieOptions());
  return response;
}

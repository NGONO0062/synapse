import "server-only";
import * as client from "openid-client";
import { authConfig } from "./config";
import { sessionFromTokens, type Session } from "./session";

let configuration: Promise<client.Configuration> | null = null;

// Découverte Keycloak mise en cache ; réessayée au prochain appel si elle échoue.
export function oidc(): Promise<client.Configuration> {
  if (!configuration) {
    const issuer = new URL(authConfig.issuer);
    // En local, Keycloak répond en HTTP : autorisé uniquement dans ce cas.
    const options = issuer.protocol === "http:" ? { execute: [client.allowInsecureRequests] } : undefined;
    configuration = client
      .discovery(issuer, authConfig.clientId, undefined, client.None(), options)
      .catch((error) => {
        configuration = null;
        throw error;
      });
  }
  return configuration;
}

export function callbackUrl(): string {
  return new URL("/auth/callback", authConfig.appUrl).toString();
}

// N'accepte qu'un chemin interne, pour éviter les redirections ouvertes.
export function safeReturnTo(value: string | null | undefined): string {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/\\") ? value : "/";
}

export async function refreshSession(session: Session): Promise<Session> {
  const tokens = await client.refreshTokenGrant(await oidc(), session.refreshToken);
  return sessionFromTokens({
    ...tokens,
    refresh_token: tokens.refresh_token ?? session.refreshToken,
    id_token: tokens.id_token ?? session.idToken,
  });
}

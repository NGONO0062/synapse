import "server-only";
import { EncryptJWT, base64url, decodeJwt, jwtDecrypt } from "jose";
import type { Role } from "@/lib/domain";
import { authConfig } from "./config";

// Session chiffrée (JWE) dans des cookies httpOnly : les jetons ne quittent jamais le serveur.
// Les jetons Keycloak dépassent la limite de 4 Ko d'un cookie, d'où le découpage en morceaux.

export type SessionUser = {
  sub: string;
  name: string;
  givenName: string | null;
  email: string | null;
  roles: Role[];
};

export type Session = {
  accessToken: string;
  refreshToken: string;
  idToken: string;
  expiresAt: number; // secondes epoch, expiration du jeton d'accès
  user: SessionUser;
};

export const SESSION_COOKIE = "sy_session";
export const FLOW_COOKIE = "sy_oidc";
const CHUNK_SIZE = 3800;
const MAX_CHUNKS = 6;
const SESSION_MAX_AGE = 60 * 60 * 12;
const ROLES: readonly Role[] = ["PO", "TESTEUR", "ADMIN"];

type CookieOptions = {
  httpOnly: boolean;
  sameSite: "lax";
  secure: boolean;
  path: string;
  maxAge: number;
};

// Sous-ensemble commun à cookies() de next/headers et à request/response.cookies.
type CookieReader = { get(name: string): { value: string } | undefined };
type CookieWriter = {
  set(name: string, value: string, options: CookieOptions): unknown;
  delete(name: string): unknown;
};

function key(): Uint8Array {
  const raw = base64url.decode(authConfig.sessionSecret);
  if (raw.length !== 32) throw new Error("SESSION_SECRET doit faire 32 octets (base64url).");
  return raw;
}

function cookieOptions(maxAge: number): CookieOptions {
  return { httpOnly: true, sameSite: "lax", secure: authConfig.secureCookies, path: "/", maxAge };
}

export async function seal(payload: Record<string, unknown>, maxAgeSeconds: number): Promise<string> {
  return new EncryptJWT(payload)
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt()
    .setExpirationTime(`${maxAgeSeconds}s`)
    .encrypt(key());
}

export async function unseal<T>(token: string): Promise<T | null> {
  try {
    const { payload } = await jwtDecrypt(token, key());
    return payload as T;
  } catch {
    return null;
  }
}

export function sessionFromTokens(tokens: {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
  expires_in?: number;
}): Session {
  if (!tokens.refresh_token || !tokens.id_token) {
    throw new Error("Réponse du fournisseur d’identité incomplète.");
  }
  const access = decodeJwt(tokens.access_token);
  const id = decodeJwt(tokens.id_token);
  const realmRoles = (access.realm_access as { roles?: string[] } | undefined)?.roles ?? [];
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    idToken: tokens.id_token,
    expiresAt: Math.floor(Date.now() / 1000) + (tokens.expires_in ?? 60),
    user: {
      sub: String(id.sub),
      name: String(id.name ?? id.preferred_username ?? id.sub),
      givenName: typeof id.given_name === "string" ? id.given_name : null,
      email: typeof id.email === "string" ? id.email : null,
      roles: ROLES.filter((r) => realmRoles.includes(r)),
    },
  };
}

export async function readSession(cookies: CookieReader): Promise<Session | null> {
  let sealed = "";
  for (let i = 0; i < MAX_CHUNKS; i++) {
    const chunk = cookies.get(`${SESSION_COOKIE}.${i}`)?.value;
    if (!chunk) break;
    sealed += chunk;
  }
  return sealed ? unseal<Session>(sealed) : null;
}

export async function writeSession(cookies: CookieWriter, session: Session): Promise<void> {
  const sealed = await seal(session, SESSION_MAX_AGE);
  const chunks = sealed.match(new RegExp(`.{1,${CHUNK_SIZE}}`, "g")) ?? [];
  if (chunks.length > MAX_CHUNKS) throw new Error("Session trop volumineuse.");
  chunks.forEach((chunk, i) => cookies.set(`${SESSION_COOKIE}.${i}`, chunk, cookieOptions(SESSION_MAX_AGE)));
  for (let i = chunks.length; i < MAX_CHUNKS; i++) cookies.delete(`${SESSION_COOKIE}.${i}`);
}

export function clearSession(cookies: CookieWriter): void {
  for (let i = 0; i < MAX_CHUNKS; i++) cookies.delete(`${SESSION_COOKIE}.${i}`);
}

export function flowCookieOptions(): CookieOptions {
  return cookieOptions(600);
}

export function isExpiring(session: Session, marginSeconds = 30): boolean {
  return session.expiresAt - marginSeconds <= Math.floor(Date.now() / 1000);
}

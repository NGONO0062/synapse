import "server-only";

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Variable d’environnement manquante : ${name} (voir web/.env.example)`);
  return value;
}

export const authConfig = {
  get appUrl() {
    return required("APP_URL");
  },
  get apiUrl() {
    return required("API_URL");
  },
  get issuer() {
    return required("OIDC_ISSUER");
  },
  get clientId() {
    return required("OIDC_CLIENT_ID");
  },
  get sessionSecret() {
    return required("SESSION_SECRET");
  },
  get secureCookies() {
    return required("APP_URL").startsWith("https://");
  },
};

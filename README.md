# Synapse

Une équipe d'agents IA conçoit, développe, teste et déploie des applications ; l'humain valide. Voir `CLAUDE.md` et `docs/Synapse_dossier_developpement.pdf`.

## Démarrer en local

```bash
# 1. Services (Postgres+pgvector, Keycloak, MinIO, LiteLLM)
cp infra/.env.example infra/.env   # remplir les mots de passe et les clés
docker compose -f infra/docker-compose.yml up -d
(cd infra && sh keycloak/set-demo-passwords.sh)   # comptes aline (PO) et brice (TESTEUR), mot de passe DEMO_USER_PASSWORD

# 2. API
cd api
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # .venv/bin/pip sous Linux/macOS
echo "SYNAPSE_DATABASE_URL=postgresql+psycopg://synapse:<POSTGRES_PASSWORD>@localhost:5432/synapse" > .env
.venv/Scripts/alembic upgrade head
.venv/Scripts/uvicorn synapse_api.main:app --reload      # http://localhost:8000/docs

# 3. Front
cd web
npm install
cp .env.example .env.local                               # puis générer SESSION_SECRET (commande dans le fichier)
npm run dev                                              # http://localhost:3200
```

Keycloak (http://localhost:8080) importe le royaume `synapse` : rôles `PO`, `TESTEUR`, `ADMIN`, thème de connexion Synapse, comptes de démo `aline` et `brice`. Le royaume n'est importé qu'au premier démarrage ; après une modification de `synapse-realm.json`, supprimer le royaume dans la console ou repartir de volumes neufs (`docker compose down -v`).

Ouvrir http://localhost:3200 : sans session, on arrive sur la connexion Keycloak, puis sur l'accueil.

## Vérifier

```bash
cd api && .venv/Scripts/python -m pytest && .venv/Scripts/python -m ruff check .
cd web && npm run typecheck && npm run lint && npm run build
```

## État d'avancement

| Lot | Contenu | État |
| --- | --- | --- |
| 0 · Fondations | Monorepo, cycle de vie des tâches, API projets/tâches/journal, auth OIDC, migration initiale, design system, écran de connexion | Fait |
| 1 · Identité | Thème de connexion Keycloak, connexion OIDC (BFF, PKCE), session chiffrée, renouvellement des jetons, garde des routes, déconnexion, accueil appelant l'API | Fait |
| 2 · Projets et tâches | Accueil, nouveau projet, barre latérale par statut, fil de tâche | À faire |
| 3 · Orchestration | LangGraph, sous-graphes par casquette, passerelle LiteLLM, bac à sable | À faire |

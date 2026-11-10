# Synapse

Plateforme où une équipe d'agents IA spécialisés (les « casquettes ») conçoit, développe, teste, documente et déploie des applications. L'humain supervise : il lance les demandes, relit les propositions et décide aux étapes clés.

Spécification complète : `docs/Synapse_dossier_developpement.pdf`. Maquettes : `docs/maquettes/` (captures) et `docs/maquettes-html/` (HTML statique de référence pour le markup et les styles).

## Règles produit non négociables

- L'IA propose, l'humain valide. Aucune étape clé ne passe sans validation humaine : exigences, maquettes, architecture, plan de chaque tâche, résultat de chaque tâche, mise en production.
- Chaque tâche a deux validations : le plan avant l'exécution, le résultat après.
- Un agent qui doit s'écarter d'un plan validé s'arrête et redemande une validation.
- La QA teste à partir des exigences validées, jamais à partir du code.
- Un bug est reproduit par un test qui échoue avant toute correction ; ce test rejoint la non-régression.
- La mise en production n'est jamais automatique.
- Aucun agent ne manipule de secret en clair : les secrets restent dans un coffre lu par la pipeline.
- Le vert dans l'interface est réservé aux décisions humaines.

## Domaine

- Rôles utilisateurs : `PO`, `TESTEUR`, `ADMIN`.
- Types de tâche : `FEATURE` (FEAT-), `BUGFIX` (BUG-), `DOC` (DOC-).
- Statuts, dans cet ordre : `BACKLOG`, `TODO`, `IN_PROGRESS`, `REVIEW`, `DONE`. Pas d'autre statut. Une tâche qui attend une réponse humaine reste `IN_PROGRESS` avec un drapeau `awaiting_human`.
- Signalement d'un bug : en langage naturel (par défaut) ou par le formulaire détaillé. Un bug écrit en langage naturel est reformulé par une casquette (titre, étapes, attendu, obtenu, environnement, gravité) ; son auteur valide la reformulation ou la fait corriger avec un commentaire. Tant qu'elle n'est pas validée, le bug reste au Backlog et ne peut pas être priorisé. Seul l'auteur du signalement valide sa reformulation.
- Transitions : BACKLOG → TODO (priorisation PO) ; TODO → IN_PROGRESS (plan validé) ; IN_PROGRESS → REVIEW (livrable contrôlé) ; REVIEW → DONE (validation humaine, plus confirmation du testeur pour un Bugfix) ; REVIEW → IN_PROGRESS (refus avec commentaires).
- Casquettes : Orchestrateur, Business Analyst, UX/UI Designer, Architecte, Développeur, Reviewer de code, Analyste de test, Automaticien, Expert sécurité, Débogueur, Rédacteur technique, DevOps. L'orchestrateur choisit la casquette ; l'utilisateur choisit seulement le modèle IA.
- Environnements : `STAGING` et `PREPROD` déployés automatiquement, `PROD` uniquement par une action humaine, avec retour arrière automatique pendant 30 min si un contrôle de santé échoue.
- Projets : création de zéro ou import d'un dépôt existant (étude du code, mémoire reconstituée, écarts spec/code tranchés par le PO, reprise des TODO et issues en Backlog).
- Mémoire du projet (versionnée dans le dépôt) : Exigences, Maquettes, Architecture, Scénarios, Tests E2E, Décisions. Elle ne contient que ce que l'humain a validé, et seul le PO la consulte (lot 4a) :
  - chaque réponse du PO à une casquette (question ou remontée) devient une décision datée, avec son auteur et sa tâche ;
  - le livrable d'une Feature propose des exigences (Business Analyst, relues par l'Analyste de test) et des scénarios (Analyste de test, écrits à partir de ces exigences, relus par le Business Analyst) ; celui d'un Bugfix, un scénario de non-régression écrit à partir du signalement validé. Le PO les valide avec le résultat ; elles entrent dans la mémoire quand la tâche passe en Done ;
  - une exigence modifiée garde son identifiant (EX-001) ; un scénario nouveau ou modifié repart à `Not started` sur les quatre plateformes, et une casquette ne fixe jamais un statut d'exécution ;
  - chaque version garde le document entier ; l'orchestrateur l'écrit dans `memoire/` sur main. Un fichier de `memoire/` écrit par un agent est ignoré ;
  - les casquettes relisent la mémoire avant chaque travail (dossier de la tâche).
  - Maquettes et Architecture seront alimentées par la création d'un projet de zéro ; Tests E2E par l'Automaticien.
- Visibilité (décision provisoire du 27/10/2026, à confirmer) : un PO voit tous les projets de l'espace ; un testeur ne voit que les bugs qu'il a signalés ; l'administrateur n'a pas accès aux projets en v1. Exception (lot 3c, provisoire) : l'administrateur voit le nom et la consommation IA de chaque projet pour fixer les quotas, et les cas de référence des casquettes (`/admin`), jamais le contenu d'un projet.
- Modèle Excel des scénarios, colonnes dans l'ordre : Module, Scénario, Préconditions, Étapes, Résultat attendu, Chrome, Firefox, iOS, Android. Statuts par plateforme : `Not started`, `Passed`, `Failed`.

## Règles chiffrées

- 3 allers-retours QA/Débogueur maximum, puis remontée au PO.
- 2 h maximum d'exécution par tâche, puis remontée au PO.
- Quota mensuel de consommation IA par projet (dollars, prix de la passerelle), fixé par l'administrateur : atteint, les casquettes s'arrêtent sur ce projet jusqu'au mois suivant.
- Retour arrière automatique actif 30 min après une mise en prod.

## Stack retenue (version 1)

- Front : Next.js, TypeScript.
- Back : Python, FastAPI.
- Données : PostgreSQL + pgvector. Fichiers : stockage objet compatible S3.
- Orchestration : LangGraph, état sauvegardé dans PostgreSQL ; un sous-graphe par casquette.
- Exécution du code généré : conteneur isolé, un par tâche.
- Accès aux modèles : passerelle unique type LiteLLM (Claude Opus, Claude Sonnet, GPT, Gemini, Mistral, modèle local plus tard).
- Identité : Keycloak (OIDC), rôles PO / TESTEUR / ADMIN. L'écran de connexion est servi par Keycloak (thème `infra/keycloak/themes/synapse`) : aucun mot de passe ne transite par Synapse. Le front est un BFF : code + PKCE, jetons gardés côté serveur dans une session chiffrée (cookies httpOnly), renouvelés par `web/src/proxy.ts`.
- Git : GitLab d'abord, GitHub ensuite.
- Hébergement : cloud privé, Kubernetes léger.

## Design

- Jetons : `design/tokens.css` et `design/tokens.json`. Ne pas inventer de couleur hors de ces jetons.
- Polices : Sora (titres), Manrope (texte), IBM Plex Mono (code et identifiants).
- Formes : boutons et étiquettes en pilule, cartes 20–22 px, barre de saisie 26 px, champs 14 px, avatars ronds.
- Logo : `web/public/logo-light.png` sur fond sombre, `web/public/logo-dark.png` sur fond clair.
- Accessibilité : contrastes WCAG AA, cibles de 44 px minimum, vrais `<button>` et `<label>`.
- Interface en français.

## Conventions de travail

- Avant d'implémenter un écran, ouvrir sa capture dans `docs/maquettes/` et son HTML dans `docs/maquettes-html/`.
- Toute nouvelle règle métier va d'abord dans ce fichier ou dans le dossier de développement.

## Organisation du dépôt

- `web/` : front Next.js 16 (lire `web/AGENTS.md` : cette version diffère des habitudes, docs dans `web/node_modules/next/dist/docs/`). Les jetons sont copiés depuis `design/tokens.css` par `npm run tokens` (automatique avant `dev` et `build`) ; ne jamais éditer `web/src/styles/tokens.css`.
- `api/` : FastAPI. Le cycle de vie des tâches est un module pur, `synapse_api/domain/lifecycle.py` : toute règle de transition s'y écrit, avec son test dans `tests/test_lifecycle.py`. Les agents n'appellent jamais l'API HTTP ; ils passent par `services.execute` avec un acteur `Actor.agent(...)`. L'orchestrateur est dans `synapse_api/agents/` : `jobs.py` dit ce qui est dû à quelle casquette (lu dans le cycle de vie), `graph.py` porte le graphe LangGraph (un sous-graphe par casquette), `execution.py` l'exécution d'une tâche (reproduction, réalisation, relecture, QA, livrable), `sandbox.py` le dépôt Git et le bac à sable Docker, `referentiels/` les référentiels versionnés. Le code généré ne s'exécute jamais hors du bac à sable. Les casquettes appellent les modèles uniquement par `gateway.py` (LiteLLM). Chaque appel passe par `usage.ask_model` (quota vérifié avant, jetons et coût enregistrés après) ; jamais `deps.model(...)` directement. La mémoire du projet est dans `synapse_api/memory.py` (contenu des documents, versions, décisions, versement au Done, rendu Markdown et Excel) ; les agents la lisent dans le dossier de la tâche et ne l'écrivent jamais. Les consignes (`graph.draft_prompt`, `jobs.review_prompt`, `execution.implementation_prompt`, `execution.requirements_prompt`, `execution.scenarios_prompt`) sont partagées avec les cas de référence (`evaluation.py`, cas dans `cas_reference/`) : une consigne modifiée se retrouve dans les deux. Un nouveau travail de casquette vient avec ses cas de référence.
- `infra/` : `docker-compose.yml` pour le développement local (Postgres+pgvector, Keycloak, MinIO, LiteLLM).
- Session côté front : les composants serveur lisent l'utilisateur via `web/src/lib/auth/current-user.ts` (derrière un `<Suspense>`) et appellent l'API via `web/src/lib/api.ts`. Ne jamais exposer un jeton à un composant client.

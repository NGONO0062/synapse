#!/usr/bin/env sh
# Donne aux comptes de d√©mo (aline : PO, brice : TESTEUR) le mot de passe DEMO_USER_PASSWORD de infra/.env.
# Usage, depuis infra/ : sh keycloak/set-demo-passwords.sh
set -eu
. ./.env
# Git Bash (Windows) rÈÈcrit les chemins /opt/... : on dÈsactive cette conversion.
export MSYS_NO_PATHCONV=1
KC="docker compose exec -T keycloak /opt/keycloak/bin/kcadm.sh"
$KC config credentials --server http://localhost:8080 --realm master --user admin --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null
for user in aline brice; do
  $KC set-password -r synapse --username "$user" --new-password "$DEMO_USER_PASSWORD"
  echo "mot de passe d√©fini pour $user"
done

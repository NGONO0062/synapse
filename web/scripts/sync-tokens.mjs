// Copie les jetons du design system (source unique : ../design/tokens.css) dans l'app.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const target = join(here, "../src/styles/tokens.css");
mkdirSync(dirname(target), { recursive: true }); // dossier absent d'un clone neuf (fichier ignoré par Git)
copyFileSync(join(here, "../../design/tokens.css"), target);

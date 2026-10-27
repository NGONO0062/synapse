// Copie les jetons du design system (source unique : ../design/tokens.css) dans l'app.
import { copyFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
copyFileSync(join(here, "../../design/tokens.css"), join(here, "../src/styles/tokens.css"));

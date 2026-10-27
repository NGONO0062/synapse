import { redirect } from "next/navigation";

// L'accueil (écran 2) arrive avec l'authentification ; en attendant, on passe par la connexion.
export default function Home() {
  redirect("/connexion");
}

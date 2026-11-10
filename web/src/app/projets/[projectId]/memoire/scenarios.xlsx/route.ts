import { NextResponse, type NextRequest } from "next/server";
import { authConfig } from "@/lib/auth/config";
import { readSession } from "@/lib/auth/session";

// Téléchargement du modèle Excel des scénarios : le jeton reste côté serveur (BFF).
export async function GET(request: NextRequest, ctx: RouteContext<"/projets/[projectId]/memoire/scenarios.xlsx">) {
  const session = await readSession(request.cookies);
  if (!session) return NextResponse.redirect(new URL("/connexion", authConfig.appUrl));
  const { projectId } = await ctx.params;
  const response = await fetch(new URL(`/projects/${encodeURIComponent(projectId)}/memory/scenarios.xlsx`, authConfig.apiUrl), {
    headers: { Authorization: `Bearer ${session.accessToken}` },
    cache: "no-store",
  });
  if (response.status === 401) return NextResponse.redirect(new URL("/connexion", authConfig.appUrl));
  if (!response.ok) return new NextResponse("Export impossible.", { status: response.status });
  return new NextResponse(response.body, {
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "application/octet-stream",
      "Content-Disposition": response.headers.get("content-disposition") ?? 'attachment; filename="scenarios.xlsx"',
      "Cache-Control": "no-store",
    },
  });
}

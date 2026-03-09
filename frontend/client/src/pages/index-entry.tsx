import { Button } from "@/components/ui/button";
import { useAuth } from "@/contexts/AuthContext";
import moioLogo from "@assets/FAVICON_MOIO_1763393251809.png";

export default function IndexEntryPage() {
  const { isAuthenticated } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/30 to-amber-50/20 px-6 py-10">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-6xl items-center">
        <div className="grid w-full gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <section className="rounded-[2rem] border border-slate-200 bg-white/90 p-10 shadow-xl backdrop-blur-sm">
            <div className="flex items-center gap-4">
              <img src={moioLogo} alt="moio" className="h-14 w-auto" />
              <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-600">
                Entry point
              </div>
            </div>
            <div className="mt-8 max-w-2xl space-y-4">
              <h1 className="text-5xl font-semibold tracking-tight text-slate-950">Moio Greenfield</h1>
              <p className="text-lg leading-8 text-slate-600">
                Selecciona qué superficie quieres abrir. El frontend principal sigue en el SPA actual. El desktop agent
                console queda separado bajo su propio namespace con las UIs originales colgadas en preview.
              </p>
            </div>
          </section>

          <section className="grid gap-5">
            <div className="rounded-[2rem] border border-slate-200 bg-white p-8 shadow-lg">
              <div className="space-y-3">
                <div className="text-sm font-semibold uppercase tracking-wide text-sky-700">Primary frontend</div>
                <h2 className="text-3xl font-semibold tracking-tight text-slate-950">Platform SPA</h2>
                <p className="text-sm leading-7 text-slate-600">
                  CRM, workflows, settings, docs y el resto del frontend activo.
                </p>
                <Button type="button" className="mt-4 w-full" onClick={() => window.location.assign(isAuthenticated ? "/dashboard" : "/login")}>
                  Entrar al frontend
                </Button>
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-200 bg-white p-8 shadow-lg">
              <div className="space-y-3">
                <div className="text-sm font-semibold uppercase tracking-wide text-amber-700">Desktop agent console</div>
                <h2 className="text-3xl font-semibold tracking-tight text-slate-950">Access Hub + Platform Admin</h2>
                <p className="text-sm leading-7 text-slate-600">
                  Namespace separado para revisar el Access Hub y la administración original del desktop agent console.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="mt-4 w-full"
                  onClick={() => window.location.assign("/desktop-agent-console/")}
                >
                  Abrir desktop agent console
                </Button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

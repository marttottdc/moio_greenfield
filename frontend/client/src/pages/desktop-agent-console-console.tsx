import AgentConsoleApp from "@/legacy-admin/vendor/components/AgentConsoleApp";
import { ensureLegacyAdminMockPreviewState, useLegacyAdminMockPreview } from "@/legacy-admin/mock-preview";
import { ensureLegacyAgentConsoleMockState, useLegacyAgentConsoleMockPreview } from "@/legacy-admin/mock-console";

export default function DesktopAgentConsoleConsolePage() {
  ensureLegacyAdminMockPreviewState();
  ensureLegacyAgentConsoleMockState();
  useLegacyAdminMockPreview();
  useLegacyAgentConsoleMockPreview();

  return (
    <div className="relative min-h-screen">
      <div className="fixed right-4 top-4 z-[100] rounded-full border border-sky-200 bg-white/95 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700 shadow-sm">
        Console preview
      </div>
      <AgentConsoleApp />
    </div>
  );
}

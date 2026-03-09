import AgentConsoleApp from "@/legacy-admin/vendor/components/AgentConsoleApp";
import { ensureLegacyAdminMockPreviewState, useLegacyAdminMockPreview } from "@/legacy-admin/mock-preview";
import { ensureLegacyAgentConsoleMockState, useLegacyAgentConsoleMockPreview } from "@/legacy-admin/mock-console";

export default function AgentConsolePage() {
  ensureLegacyAdminMockPreviewState();
  ensureLegacyAgentConsoleMockState();
  useLegacyAdminMockPreview();
  useLegacyAgentConsoleMockPreview();

  return <AgentConsoleApp />;
}

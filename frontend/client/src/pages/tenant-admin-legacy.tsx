import TenantAdminApp from "@/legacy-admin/vendor/components/TenantAdminApp";
import { ensureLegacyAdminMockPreviewState, useLegacyAdminMockPreview } from "@/legacy-admin/mock-preview";

export default function TenantAdminLegacyPage() {
  ensureLegacyAdminMockPreviewState();
  useLegacyAdminMockPreview();

  return (
    <div className="relative min-h-screen">
      <div className="fixed right-4 top-4 z-[100] rounded-full border border-sky-200 bg-white/95 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-sky-700 shadow-sm">
        Preview mock
      </div>
      <TenantAdminApp />
    </div>
  );
}

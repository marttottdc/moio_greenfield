/**
 * Shopify app install entry – /apps/shopify/install
 * If ?shop= is present, redirects to backend OAuth install. Otherwise asks user to open from Shopify Admin.
 */
import { useEffect } from "react";

export default function ShopifyAppInstallPage() {
  const shop = new URLSearchParams(typeof window !== "undefined" ? window.location.search : "").get("shop");

  useEffect(() => {
    if (shop && typeof window !== "undefined") {
      const host = new URLSearchParams(window.location.search).get("host") || "";
      const base = window.location.origin;
      const installUrl = `${base}/api/v1/integrations/shopify/oauth/install/?shop=${encodeURIComponent(shop)}${host ? `&host=${encodeURIComponent(host)}` : ""}`;
      window.location.href = installUrl;
    }
  }, [shop]);

  if (shop) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-[3px] border-[#008060] border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Redirecting to install…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
      <div className="bg-white border border-gray-200 rounded-xl p-8 max-w-sm text-center shadow">
        <p className="text-gray-800 font-semibold mb-1">Open from Shopify Admin</p>
        <p className="text-sm text-gray-500">
          Install or open this app from your Shopify admin (Apps) to continue.
        </p>
      </div>
    </div>
  );
}

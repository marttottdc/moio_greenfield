/**
 * Shopify app error page – shown at /apps/shopify/error?message=...
 */
import { useSearch } from "wouter";

export default function ShopifyAppErrorPage() {
  const search = useSearch();
  const params = new URLSearchParams(search);
  const message = params.get("message") || "Something went wrong. Try opening the app again from Shopify Admin.";

  return (
    <div className="flex items-center justify-center min-h-screen bg-[#f6f6f7]">
      <div className="bg-white border border-red-200 rounded-xl p-8 max-w-sm text-center shadow">
        <p className="text-red-600 font-semibold mb-1">Error</p>
        <p className="text-sm text-gray-500">{message}</p>
      </div>
    </div>
  );
}

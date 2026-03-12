/**
 * Shopify app landing page – /apps/shopify
 *
 * Standalone landing for the moio Shopify app: value proposition, features,
 * and CTA to install or open from Shopify Admin. Renders without app shell.
 */

import { Link } from "wouter";
import moioLogo from "@assets/Moio_New_Logo_Transparent_1764783655330.png";
import { SHOPIFY_APP_PATH } from "@/constants/shopify";

function useSearchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

export default function ShopifyLandingPage() {
  const shop = useSearchParam("shop");
  const host = useSearchParam("host");
  const installUrl =
    typeof window !== "undefined"
      ? `${window.location.origin}/api/v1/integrations/shopify/oauth/install/?shop=${encodeURIComponent(shop)}${host ? `&host=${encodeURIComponent(host)}` : ""}`
      : "#";

  return (
    <div className="min-h-screen bg-[#f6f6f7] font-sans">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white/80 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <img
            src={moioLogo}
            alt="moio"
            className="h-8 w-auto object-contain"
          />
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
            for Shopify
          </span>
        </div>
      </header>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-4 sm:px-6 pt-16 pb-12 text-center">
        <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 tracking-tight">
          Connect your store to moio
        </h1>
        <p className="mt-4 text-lg text-gray-600 max-w-xl mx-auto">
          Sync products, customers, and orders from Shopify into your CRM. One
          place for your sales and customer data.
        </p>

        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          {shop ? (
            <a
              href={installUrl}
              className="inline-flex items-center justify-center rounded-lg bg-[#008060] px-6 py-3 text-base font-semibold text-white shadow-sm hover:bg-[#006e52] transition-colors"
            >
              Install app
            </a>
          ) : (
            <p className="text-sm text-gray-500 max-w-sm">
              Open this app from your Shopify admin (Apps → moio) to install and
              connect your store.
            </p>
          )}
          {shop && (
            <Link
              href={`${SHOPIFY_APP_PATH}?shop=${encodeURIComponent(shop)}${host ? `&host=${encodeURIComponent(host)}` : ""}`}
              className="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-6 py-3 text-base font-medium text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Already installed? Open app
            </Link>
          )}
        </div>
      </section>

      {/* Features */}
      <section className="max-w-3xl mx-auto px-4 sm:px-6 py-12 border-t border-gray-200/80">
        <h2 className="text-xl font-semibold text-gray-900 mb-8 text-center">
          What you get
        </h2>
        <ul className="grid sm:grid-cols-3 gap-8">
          <li className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-xl bg-[#008060]/10 flex items-center justify-center mb-3">
              <svg
                className="w-6 h-6 text-[#008060]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                />
              </svg>
            </div>
            <span className="font-medium text-gray-900">Products</span>
            <span className="text-sm text-gray-500 mt-1">
              Sync your catalog to moio
            </span>
          </li>
          <li className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-xl bg-[#008060]/10 flex items-center justify-center mb-3">
              <svg
                className="w-6 h-6 text-[#008060]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                />
              </svg>
            </div>
            <span className="font-medium text-gray-900">Customers</span>
            <span className="text-sm text-gray-500 mt-1">
              Keep contacts in sync
            </span>
          </li>
          <li className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-xl bg-[#008060]/10 flex items-center justify-center mb-3">
              <svg
                className="w-6 h-6 text-[#008060]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
                />
              </svg>
            </div>
            <span className="font-medium text-gray-900">Orders</span>
            <span className="text-sm text-gray-500 mt-1">
              Orders flow into your CRM
            </span>
          </li>
        </ul>
      </section>

      {/* Footer note */}
      <footer className="max-w-3xl mx-auto px-4 sm:px-6 py-8 text-center">
        <p className="text-xs text-gray-400">
          moio × Shopify — connect your store in a few clicks.
        </p>
      </footer>
    </div>
  );
}

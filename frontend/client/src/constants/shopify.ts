/**
 * Shopify embedded app route namespace.
 * Must stay in sync with backend SHOPIFY_APP_PATH (central_hub.integrations.shopify.views).
 */
export const SHOPIFY_APP_PATH = "/apps/shopify/app";
export const SHOPIFY_APP_NAMESPACE = "/apps/shopify";

/** True if location is under the Shopify embedded app (no shell). */
export function isShopifyAppRoute(location: string): boolean {
  return (
    location.startsWith(SHOPIFY_APP_PATH) ||
    location === SHOPIFY_APP_NAMESPACE ||
    location.startsWith(`${SHOPIFY_APP_NAMESPACE}/`)
  );
}

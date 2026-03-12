"""
Shopify API Client

Handles authentication, rate limiting, and API calls to Shopify Admin API.
Supports GraphQL and REST API endpoints for products, orders, and customers.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Union

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class ShopifyAPIError(Exception):
    """Shopify API Error"""
    pass


class ShopifyRateLimitError(ShopifyAPIError):
    """Rate limit exceeded"""
    pass


class ShopifyAPIClient:
    """
    Shopify Admin API client supporting both REST and GraphQL endpoints.

    Handles authentication, rate limiting, and pagination automatically.
    """

    def __init__(
        self,
        store_url: str,
        access_token: str,
        api_version: str = "2024-01",
        timeout: int = 30,
        max_retries: int = 3
    ):
        """
        Initialize Shopify API client.

        Args:
            store_url: Shopify store URL (e.g., 'mystore.myshopify.com')
            access_token: Shopify Admin API access token
            api_version: API version to use
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for rate-limited requests
        """
        self.store_url = store_url.rstrip('/')
        self.access_token = access_token
        self.api_version = api_version
        self.timeout = timeout
        self.max_retries = max_retries

        # Rate limiting tracking
        self.request_count = 0
        self.reset_time = None
        self.bucket_size = 40  # Shopify allows 40 requests per second for most apps

        # Session for connection reuse
        self.session = requests.Session()
        self.session.headers.update({
            'X-Shopify-Access-Token': self.access_token,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    def _get_rest_url(self, endpoint: str) -> str:
        """Get full REST API URL for endpoint."""
        return f"https://{self.store_url}/admin/api/{self.api_version}/{endpoint}.json"

    def _get_graphql_url(self) -> str:
        """Get GraphQL API URL."""
        return f"https://{self.store_url}/admin/api/{self.api_version}/graphql.json"

    def _handle_rate_limit(self, response: requests.Response) -> None:
        """
        Handle Shopify rate limiting.

        Shopify uses a leaky bucket algorithm. When rate limited,
        we need to wait until the bucket resets.
        """
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                wait_time = int(retry_after)
            else:
                # Default backoff - wait for bucket reset
                wait_time = 1

            logger.warning(f"Rate limited. Waiting {wait_time} seconds.")
            time.sleep(wait_time)
            return

        # Update rate limit tracking
        request_id = response.headers.get('X-Shopify-Request-Id')
        if request_id:
            self.request_count += 1

            # Check bucket capacity (simplified)
            if self.request_count >= self.bucket_size:
                logger.warning("Approaching rate limit. Slowing down.")
                time.sleep(0.1)

    def _make_request(
        self,
        method: str,
        url: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        retry_count: int = 0
    ) -> requests.Response:
        """
        Make HTTP request with automatic retry and rate limit handling.
        """
        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=self.timeout
            )

            self._handle_rate_limit(response)

            # Handle rate limiting with retry
            if response.status_code == 429 and retry_count < self.max_retries:
                logger.warning(f"Rate limited, retrying ({retry_count + 1}/{self.max_retries})")
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(method, url, data, params, retry_count + 1)

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            if retry_count < self.max_retries:
                logger.warning(f"Request failed, retrying ({retry_count + 1}/{self.max_retries}): {e}")
                time.sleep(2 ** retry_count)
                return self._make_request(method, url, data, params, retry_count + 1)
            msg = f"API request failed after {self.max_retries} retries: {e}"
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code == 403:
                msg += (
                    " (403 Forbidden: the access token may lack required scopes. "
                    "Re-run the Shopify install from the app so a new token is issued with read_products, read_customers, read_orders, read_inventory.)"
                )
            elif status_code == 401:
                msg += (
                    " (401 Unauthorized: the access token may be invalid or expired. "
                    "Re-run the Shopify install from the app to get a new token.)"
                )
            raise ShopifyAPIError(msg)

    def _paginate_rest(self, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Handle REST API pagination automatically.

        Returns all results from a paginated endpoint.
        """
        results = []
        url = self._get_rest_url(endpoint)

        while url:
            response = self._make_request('GET', url, params=params)
            data = response.json()

            # Extract resource name from endpoint
            resource = endpoint.split('/')[-1]  # e.g., 'products' from 'products'
            if resource in data:
                results.extend(data[resource])

            # Check for next page
            link_header = response.headers.get('Link', '')
            next_url = None
            if 'rel="next"' in link_header:
                # Parse Link header for next URL
                links = link_header.split(',')
                for link in links:
                    if 'rel="next"' in link:
                        next_url = link.split(';')[0].strip().strip('<>')
                        break

            url = next_url
            params = None  # Only use params on first request

        return results

    # ============================================================================
    # PRODUCTS
    # ============================================================================

    def get_products(self, params: Optional[Dict] = None) -> List[Dict]:
        """
        Get all products with pagination.

        Args:
            params: Query parameters (limit, since_id, etc.)
        """
        return self._paginate_rest('products', params)

    def get_product(self, product_id: Union[str, int]) -> Dict:
        """Get single product by ID."""
        url = self._get_rest_url(f'products/{product_id}')
        response = self._make_request('GET', url)
        return response.json()['product']

    def create_product(self, product_data: Dict) -> Dict:
        """Create new product."""
        url = self._get_rest_url('products')
        response = self._make_request('POST', url, data={'product': product_data})
        return response.json()['product']

    def update_product(self, product_id: Union[str, int], product_data: Dict) -> Dict:
        """Update existing product."""
        url = self._get_rest_url(f'products/{product_id}')
        response = self._make_request('PUT', url, data={'product': product_data})
        return response.json()['product']

    def delete_product(self, product_id: Union[str, int]) -> None:
        """Delete product."""
        url = self._get_rest_url(f'products/{product_id}')
        self._make_request('DELETE', url)

    # ============================================================================
    # CUSTOMERS
    # ============================================================================

    def get_customers(self, params: Optional[Dict] = None) -> List[Dict]:
        """
        Get all customers with pagination.

        Args:
            params: Query parameters (limit, since_id, etc.)
        """
        return self._paginate_rest('customers', params)

    def get_customer(self, customer_id: Union[str, int]) -> Dict:
        """Get single customer by ID."""
        url = self._get_rest_url(f'customers/{customer_id}')
        response = self._make_request('GET', url)
        return response.json()['customer']

    def create_customer(self, customer_data: Dict) -> Dict:
        """Create new customer."""
        url = self._get_rest_url('customers')
        response = self._make_request('POST', url, data={'customer': customer_data})
        return response.json()['customer']

    def update_customer(self, customer_id: Union[str, int], customer_data: Dict) -> Dict:
        """Update existing customer."""
        url = self._get_rest_url(f'customers/{customer_id}')
        response = self._make_request('PUT', url, data={'customer': customer_data})
        return response.json()['customer']

    def delete_customer(self, customer_id: Union[str, int]) -> None:
        """Delete customer."""
        url = self._get_rest_url(f'customers/{customer_id}')
        self._make_request('DELETE', url)

    # ============================================================================
    # ORDERS
    # ============================================================================

    def get_orders(self, params: Optional[Dict] = None) -> List[Dict]:
        """
        Get all orders with pagination.

        Args:
            params: Query parameters (limit, since_id, status, etc.)
        """
        return self._paginate_rest('orders', params)

    def get_order(self, order_id: Union[str, int]) -> Dict:
        """Get single order by ID."""
        url = self._get_rest_url(f'orders/{order_id}')
        response = self._make_request('GET', url)
        return response.json()['order']

    def create_order(self, order_data: Dict) -> Dict:
        """Create new order."""
        url = self._get_rest_url('orders')
        response = self._make_request('POST', url, data={'order': order_data})
        return response.json()['order']

    def update_order(self, order_id: Union[str, int], order_data: Dict) -> Dict:
        """Update existing order."""
        url = self._get_rest_url(f'orders/{order_id}')
        response = self._make_request('PUT', url, data={'order': order_data})
        return response.json()['order']

    def delete_order(self, order_id: Union[str, int]) -> None:
        """Delete order."""
        url = self._get_rest_url(f'orders/{order_id}')
        self._make_request('DELETE', url)

    # ============================================================================
    # WEBHOOKS
    # ============================================================================

    def get_webhooks(self) -> List[Dict]:
        """Get all webhooks."""
        return self._paginate_rest('webhooks')

    def create_webhook(self, webhook_data: Dict) -> Dict:
        """
        Create webhook subscription.

        Shopify's webhook registration is more reliable through Admin GraphQL,
        especially for compliance topics such as customers/data_request,
        customers/redact, shop/redact, and app/uninstalled.
        """
        topic = str(webhook_data.get("topic") or "").strip()
        callback_url = str(webhook_data.get("address") or "").strip()
        if not topic or not callback_url:
            raise ShopifyAPIError("Webhook topic and address are required")

        graphql_topic = topic.replace("/", "_").replace(".", "_").upper()
        mutation = """
        mutation webhookSubscriptionCreate($topic: WebhookSubscriptionTopic!, $webhookSubscription: WebhookSubscriptionInput!) {
          webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
            userErrors {
              field
              message
            }
            webhookSubscription {
              id
              topic
              endpoint {
                __typename
                ... on WebhookHttpEndpoint {
                  callbackUrl
                }
              }
            }
          }
        }
        """
        result = self.graphql_query(
            mutation,
            variables={
                "topic": graphql_topic,
                "webhookSubscription": {
                    "callbackUrl": callback_url,
                    "format": "JSON",
                },
            },
        )
        payload = (
            result.get("data", {})
            .get("webhookSubscriptionCreate", {})
        )
        user_errors = payload.get("userErrors") or []
        if user_errors:
            joined = "; ".join(err.get("message", "Unknown Shopify webhook error") for err in user_errors)
            raise ShopifyAPIError(f"Webhook subscription failed: {joined}")

        subscription = payload.get("webhookSubscription") or {}
        if not subscription:
            raise ShopifyAPIError("Webhook subscription failed: no subscription returned")

        endpoint = subscription.get("endpoint") or {}
        return {
            "id": subscription.get("id", ""),
            "topic": subscription.get("topic", topic),
            "address": endpoint.get("callbackUrl", callback_url),
        }

    def delete_webhook(self, webhook_id: Union[str, int]) -> None:
        """Delete webhook."""
        url = self._get_rest_url(f'webhooks/{webhook_id}')
        self._make_request('DELETE', url)

    # ============================================================================
    # GRAPHQL
    # ============================================================================

    def graphql_query(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """
        Execute GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables
        """
        url = self._get_graphql_url()
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        response = self._make_request('POST', url, data=payload)
        result = response.json()

        if 'errors' in result:
            raise ShopifyAPIError(f"GraphQL errors: {result['errors']}")

        return result

    # ============================================================================
    # UTILITY METHODS
    # ============================================================================

    def get_shop_info(self) -> Dict:
        """Get basic shop information."""
        url = self._get_rest_url('shop')
        response = self._make_request('GET', url)
        return response.json()['shop']

    def test_connection(self) -> bool:
        """Test API connection by fetching shop info."""
        try:
            self.get_shop_info()
            return True
        except Exception as e:
            logger.error(f"Shopify API connection test failed: {e}")
            return False

    def get_inventory_levels(self, inventory_item_ids: List[Union[str, int]]) -> List[Dict]:
        """Get inventory levels for multiple items."""
        ids_param = ','.join(str(id) for id in inventory_item_ids)
        url = self._get_rest_url('inventory_levels')
        params = {'inventory_item_ids': ids_param}
        response = self._make_request('GET', url, params=params)
        return response.json()['inventory_levels']

    def get_inventory_levels_by_location(
        self, location_id: Union[str, int], limit: int = 1
    ) -> List[Dict]:
        """Get inventory levels at a location (tests read_inventory scope)."""
        url = self._get_rest_url('inventory_levels')
        params = {'location_ids': str(location_id), 'limit': limit}
        response = self._make_request('GET', url, params=params)
        return response.json().get('inventory_levels', [])


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def extract_shopify_id(gid: str) -> str:
    """
    Extract numeric ID from Shopify GraphQL Global ID.

    Example: 'gid://shopify/Product/123456789' -> '123456789'
    """
    return gid.split('/')[-1] if gid else ''


def format_shopify_money(amount: Union[str, float, int]) -> str:
    """Format money amount for Shopify API."""
    return f"{float(amount):.2f}"


def parse_shopify_timestamp(timestamp: str) -> timezone.datetime:
    """Parse Shopify timestamp string to Django datetime."""
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(timestamp)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt
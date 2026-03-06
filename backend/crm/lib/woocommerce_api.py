from itertools import product
from django.utils import timezone
from woocommerce import API


def get_product_price(product):
    try:
        return float(product["price"])
    except ValueError:
        return 0


def get_product_sale_price(product):
    try:
        return float(product["sale_price"])
    except ValueError:
        return 0


def get_product_main_image(product):
    if len(product["images"]) >0:
        return product["images"][0]["src"]
    return None


def get_product_brand(product):
    return ""


def get_product_category(product):
    return ""


def get_product_tags(product):
    return product["tags"]


class WooCommerceAPI:

    def __init__(self, url, consumer_key, consumer_secret, timeout=5):

        self.url = url
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.wcapi = API(
            url=self.url,
            consumer_key=self.consumer_key,
            consumer_secret=self.consumer_secret,
            wp_api=True,
            version="wc/v3",
            timeout=timeout
        )

    def create_product(self, name, product_type, description, short_description, sku, manage_stock="false"):
        data = {
            "name": name,
            "sku": sku,
            "type": product_type,
            "description": description,
            "short_description": short_description,
            "manage_stock": manage_stock,
            "status": "draft"

        }

        response = self.wcapi.post("products", data).json()

        print("Ended creating product, todo process result")
        return response

    def load_colors(self):
        response = self.wcapi.get(f"products/attributes/1/terms/?per_page=100").json()

        colors = []

        for r in response:

            color = {
                "id": r["id"],
                "name": r["name"],
                "slug": r["slug"],
                "count": r["count"]
            }
            colors.append(color)

        return colors

    def get_color_attr(self, color_slug):

        if not self.colors:
            self.load_colors()

        for item in self.colors:
            color_slug = color_slug.lower()
            color_slug = color_slug.replace("/", "-")
            if item['slug'] == color_slug:
                return item['name']

    def load_sizes(self):
        response = self.wcapi.get(f"products/attributes/3/terms/?per_page=100").json()
        sizes = []
        for r in response:
            size = {
                "id": r["id"],
                "name": r["name"],
                "slug": r["slug"],
                "count": r["count"]
            }
            sizes.append(size)

        return sizes

    def get_size_attr(self, size_slug):

        for item in self.sizes:
            if item['slug'] == size_slug:
                return item['name']

    def create_product_variant(self, parent_product_id, variant_sku, description, manage_stock, regular_price, stock_qty, attributes, status, sale_price="", max_retries=5):

        if float(regular_price) > 0:
            status = "publish"
        else:
            status = "draft"

        data = {
                "sku": variant_sku,
                "manage_stock": manage_stock,
                "description": description,
                "regular_price": regular_price,
                "sale_price": sale_price,
                "status": status,
                "stock_quantity": stock_qty,
                "attributes": attributes,
            }
        retries = 0
        while retries <= max_retries:
            try:
                response = self.wcapi.post(f"products/{parent_product_id}/variations", data)
                if response.status_code == 200:
                    woo_response = response.json()
                    print(f'Variant Updated: SKU:{woo_response["sku"]} | Description:{woo_response["description"]}')
                    print(f'Price:{woo_response["regular_price"]} | Sale Price:{woo_response["sale_price"]} | Stock:{woo_response["stock_quantity"]} | Status:{woo_response["status"]}')
                    print(f'Link:{woo_response["permalink"]}')
                    return response.json()
                else:
                    return None

            except Exception as e:
                print(e)
                retries += 1
        print("Max retries reached")
        return None

    def update_product_variant(self, parent_product_id, variant_id, status, stock_qty, regular_price, attributes, description="", short_description="", sale_price="", max_retries=5):

        if float(regular_price) > 0:
            status = "publish"
        else:
            status = "draft"

        data = {
            "description": description,
            "regular_price": regular_price,
            "status": status,
            "stock_quantity": stock_qty,
            "sale_price": sale_price,
            "attributes": attributes
        }
        retries = 0
        while retries <= max_retries:
            try:
                response = self.wcapi.post(f"products/{parent_product_id}/variations/{variant_id}", data)
                if response.status_code == 200:
                    woo_response = response.json()
                    print(f'Variant Updated: SKU:{woo_response["sku"]} | Description:{woo_response["description"]}')
                    print(f'Price:{woo_response["regular_price"]} | Sale Price:{woo_response["sale_price"]} | Stock:{woo_response["stock_quantity"]} | Status:{woo_response["status"]}')
                    print(f'Link:{woo_response["permalink"]}')
                    return response.json()
                else:
                    print(response.json())
                    return None

            except Exception as e:
                print(e)
                retries += 1

        print("Max retries reached")
        return None

    def create_product_attributes(self, color_slug, size_slug):

        color = self.get_color_attr(color_slug)
        size = self.get_size_attr(size_slug)

        if color is None or size is None:
            return None

        attributes = [
            {"id": 1, "name": "Color", "option": color},
            {"id": 3, "name": "Talle", "option": size}
        ]

        print(f'Color: {attributes[0]["option"]} | Talle: {attributes[1]["option"]}')
        return attributes

    def get_orders(self):
        # Initialize an empty list to store all orders
        all_orders = []

        # Set initial page number
        page = 1

        while True:
            # Get orders from the current page
            response = self.wcapi.get(f"orders?page={page}&per_page=10")

            if response.status_code != 200:  # Check if the response is successful
                print(f"Failed to retrieve orders: {response.status_code}")
                break

            orders = response.json()  # Parse response JSON

            if not orders:  # Check if the list of orders is empty
                break
            all_orders.extend(orders)  # Add the orders from the current page to the all_orders list
            page += 1  # Increment the page number

        return all_orders

    def get_order(self, order_id):
        response = self.wcapi.get(f"orders/{order_id}")

        if response.status_code == 200:
            return response.json()
        else:
            return None

    def get_product(self, sku: str, max_retries=5):

            # Get List of Orders
            retries = 0
            while retries <= max_retries:
                try:
                    products = self.wcapi.get(f"products?sku={sku}").json()

                    if len(products) == 0:
                        print("Product not found")
                        return None

                    else:
                        product = products[0]
                        print(product["id"], product["sku"], product["name"], product["type"], product["status"])
                        return product["id"]

                except Exception as e:

                    print(e)
                    retries += 1

            print("No response from endpoint")
            return None

    def get_variants(self, product_id, sku: str, verbose=False):

        variants = self.wcapi.get(f"products/{product_id}/variations?sku={sku}").json()

        if len(variants) == 0:
            print("Variant not found")
            return None

        for variation in variants:
            variation_id = variation["id"]
            variation_sku = variation["sku"]
            variation_manage_stock = variation["manage_stock"]
            variation_description = variation["description"]
            variation_prince = variation["price"]
            variation_regular_price = variation["regular_price"]
            variation_sale_price = variation["sale_price"]
            variation_status = variation["status"]
            variation_stock_qty = variation["stock_quantity"]
            variation_attibutes = variation["attributes"]

        if verbose:
            print(variants)

        return variants[0]

    def get_customers(self):

        # Get List of Customers
        customers = self.wcapi.get("customers?page=2").json()

        # Loop through orders and print the id
        for customer in customers:
            print("id:", customer["id"])
            print("date created:", customer["date_created"])
            print("email:", customer["email"])
            print("first name:", customer["first_name"])
            print("last name:", customer["last_name"])
            print("username:", customer["username"])
            print("is paying customer:", customer["is_paying_customer"])
            print("-----------------------------------------")

    def delete_variation(self, parent_id, variation_id):
        print(self.wcapi.delete(f"products/{parent_id}/variations/{variation_id}", params={"force": True}).json())

    def get_product_details(self, product_id):

        response = self.wcapi.get(f"products/{product_id}").json()

        if "id" in response:
            print(f"Product ID: {response['id']}")
            print(f"Product Name: {response['name']}")
            print(f"Product Type: {response['type']}")
            print(f"Regular Price: {response['regular_price']}")
            print(f"Sale Price: {response['sale_price']}")
            print(f"Stock Status: {response['stock_status']}")
            print(f"Attributes: {response['attributes']}")
        else:
            print(f"Failed to fetch product details: {response.get('message', 'Unknown error')}")

    def create_or_update_attribute_options(self, product_id, new_attributes):
        # Fetch existing product details
        response = self.wcapi.get(f"products/{product_id}").json()

        existing_attributes = response.get("attributes", [])

        # Loop through each new attribute to add
        for new_attr in new_attributes:
            attribute_id = new_attr['id']
            new_option = new_attr['option']

            # Locate the existing attribute by its ID
            existing_attribute = next((attr for attr in existing_attributes if attr['id'] == attribute_id), None)

            if existing_attribute:
                # Add the new option only if it doesn't exist
                if new_option not in existing_attribute['options']:
                    existing_attribute['options'].append(new_option)
            else:
                # Create a new attribute if it doesn't exist
                new_attribute = {
                    "id": attribute_id,
                    "options": [new_option],
                    "visible": True,
                    "variation": True
                }
                existing_attributes.append(new_attribute)

        # Update the product with the modified attributes
        update_data = {
                "attributes": existing_attributes,
                "manage_stock": False,
                "status": "publish"
        }
        response = self.wcapi.put(f"products/{product_id}", update_data).json()

        # Check for successful update
        if "id" in response:
            print(f"Successfully updated or created attributes for product {product_id}.")
        else:
            print(f"Failed to update or create attributes: {response.get('message', 'Unknown error')}")

    def get_list_product_variants(self):
        page = 1
        variantes = []
        products = self.wcapi.get("products?page=1&per_page=100").json()
        while len(products) > 0:
            page += 1
            for p in products:

                if p["status"] == "publish":
                    prod_id = p["id"]

                    variations = self.wcapi.get(f"products/{prod_id}/variations/?per_page=50").json()
                    variantes.extend(variations)

            products = self.wcapi.get(f"products?page={page}&per_page=100").json()

        print("lista de productos descargada")
        return variantes

    def mark_order_as_synced(self, order):

        now_utc = timezone.now()
        now = timezone.localtime(now_utc)
        meta_data = order.get("meta_data", [])
        meta_data.append({"key": "synced", "value": now.strftime("%Y-%m-%d %H:%M:%S") })
        data = {"meta_data": meta_data}
        order_id = order["id"]
        self.wcapi.put(f"orders/{order_id}", data)

        data = {
            "note": f"Pedido sincronizado a Zeta Software {now}"
        }
        self.wcapi.post(f"orders/{order_id}/notes", data)

    def mark_order_as_sent_to_process(self, order):

        now_utc = timezone.now()
        now = timezone.localtime(now_utc)

        meta_data = order.get("meta_data", [])
        meta_data.append({"key": "sent_to_dac", "value": now.strftime("%Y-%m-%d %H:%M:%S") })
        data = {"meta_data": meta_data}
        order_id = order["id"]
        try:
            self.wcapi.put(f"orders/{order_id}", data)
        except Exception as e:
            print(e)

    def inform_tracking_code(self, order, tracking_code):

        now_utc = timezone.now()
        now = timezone.localtime(now_utc)

        meta_data = order.get("meta_data", [])
        meta_data.append({"key": "tracking_code", "value": tracking_code})
        data = {"meta_data": meta_data}
        order_id = order["id"]
        try:
            self.wcapi.put(f"orders/{order_id}", data)
        except Exception as e:
            print(e)

    def add_note_to_customer(self, order, note):

        order_id = order["id"]
        data = {
            "note": note,
            "customer_note": True
        }
        try:
            self.wcapi.post(f"orders/{order_id}/notes", data)
        except Exception as e:
            print(e)


    def is_synced(self, order):
        meta_data = order.get("meta_data")

        for item in meta_data:
            if item["key"] == "synced":
                return True
        else:
            return False


    def sent_to_dac(self, order):
        meta_data = order.get("meta_data")

        for item in meta_data:
            if item["key"] == "sent_to_dac":
                return True
        else:
            return False

    def get_city_country(self, country, city):

        data = self.wcapi.get(f"data/countries/{country}").json()

        city_name = ""
        for state in data["states"]:
            if city in state["code"]:
                city_name = state["name"]
                break

        response = {
            "country_name": data["name"],
            "city_name": city_name
        }
        return response

    def woo_address_formatted_for_dac(self, billing):

        country_data = self.get_city_country(billing["country"], billing["state"][2:])
        flat = f'{billing["address_1"]},{billing["city"]}, {country_data["city_name"]},{country_data["country_name"]}'

        return flat

    def mark_as_completed(self, order):

        order_id = order["number"]

        data = {
            "status": "completed"
        }

        self.wcapi.put(f"orders/{order_id}", data)

    def get_product_id(self, sku: str, max_retries=5):
        # Get List of Orders
        retries = 0
        while retries <= max_retries:
            try:
                products = self.wcapi.get(f"products?sku={sku}").json()

                if len(products) == 0:
                    print("Product not found")
                    return None

                else:
                    product = products[0]
                    return product["id"]

            except Exception as e:

                print(e)
                retries += 1

        print("No response from endpoint")
        return None

    def get_variant(self, product_id, sku: str, verbose=False):

        variant = self.wcapi.get(f"products/{product_id}/variations?sku={sku}").json()

        if len(variant) == 0:
            print("Variant not found")
            return None

        return variant

    def update_variant(self, product_id, variant_data, max_retries=5):

        variant_id = variant_data["id"]

        retries = 0
        while retries <= max_retries:
            try:
                response = self.wcapi.post(f"products/{product_id}/variations/{variant_id}", variant_data)
                if response.status_code == 200:
                    return response.json()

            except Exception as e:
                print(e)
                retries += 1

        print("Max retries reached")
        return None

    def get_products(self, max_retries=5):
        """
        Fetch all products from WooCommerce API with pagination and retry mechanism.

        Args:
            max_retries (int): Maximum number of retry attempts per page (default: 5)

        Returns:
            list: List of all products retrieved, or partial list if fetching fails

        """
        all_products = []
        page = 1

        while True:
            for attempt in range(max_retries + 1):  # +1 because range is exclusive of end
                try:
                    # Fetch products for the current page
                    response = self.wcapi.get(f"products?page={page}").json()

                    # Check if response is empty indicating last page
                    if not response:
                        return all_products

                    # Add products to the master list
                    all_products.extend(response)
                    break  # Success, move to next page

                except Exception as e:
                    if attempt < max_retries:
                        print(f"Attempt {attempt + 1} failed for page {page}: {e}")
                        continue
                    else:
                        print(f"Max retries ({max_retries}) exceeded for page {page}: {e}")
                        return all_products  # Return what we have rather than failing completely

            page += 1

    def get_all_variants(self, product_id):

        variants = self.wcapi.get(f"products/{product_id}/variations").json()

        if len(variants) == 0:
            print("Variants not found")
            return []

        return variants

    def create_woocommerce_order(self, customer_data, products):
        """
        Create a WooCommerce order and return the order number.

        Args:
            customer_data (dict): Customer information (email, first_name, last_name, etc.)
            products (list): List of product dictionaries containing id and quantity

        Returns:
            str: Order number if successful, None if failed
        """
        try:

            # Prepare order data
            order_data = {
                "payment_method": "cod",  # Can be changed to other payment methods
                "payment_method_title": "Cash on Delivery",
                "set_paid": False,
                "billing": {
                    "first_name": customer_data.get("first_name", ""),
                    "last_name": customer_data.get("last_name", ""),
                    "address_1": customer_data.get("address_1", ""),
                    "address_2": customer_data.get("address_2", ""),
                    "city": customer_data.get("city", ""),
                    "state": customer_data.get("state", ""),
                    "postcode": customer_data.get("postcode", ""),
                    "country": customer_data.get("country", "US"),
                    "email": customer_data.get("email", ""),
                    "phone": customer_data.get("phone", "")
                },
                "shipping": customer_data.get("shipping", {}),
                "line_items": [
                    {
                        "product_id": product["id"],
                        "quantity": product["quantity"]
                    } for product in products
                ],
                "status": "processing"  # Can be 'pending', 'completed', etc.
            }

            # Create the order
            response = self.wcapi.post("orders", order_data)

            if response.status_code == 201:
                order = response.json()
                return order["number"]
            else:
                print(f"Error creating order: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"Exception occurred while creating order: {str(e)}")
            return None



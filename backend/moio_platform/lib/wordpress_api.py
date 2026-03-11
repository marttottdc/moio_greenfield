import requests
from bs4 import BeautifulSoup


def extract_content_with_hierarchy(html):
    def parse_element(element):
        """Recursively process each element and retain meaningful content in a hierarchical structure."""
        result = {}
        # Get tag name
        if element.name:
            result['tag'] = element.name

        # Capture meaningful content
        text_content = element.get_text(strip=True)
        if text_content:
            result['text'] = text_content

        # Extract links
        if element.name == 'a' and element.get('href'):
            result['href'] = element['href']

        # Extract images
        if element.name == 'img' and element.get('src'):
            result['src'] = element['src']

        # Process children recursively
        children = [parse_element(child) for child in element.children if child.name]
        if children:
            result['children'] = children

        return result

    # Parse the HTML
    soup = BeautifulSoup(html, 'html.parser')

    # Start processing from the body tag (or the root if no body)
    root_element = soup.body if soup.body else soup
    return parse_element(root_element)


class WordPressAPIClient:
    """
    A small helper class to interact with the WordPress REST API.
    Assumes Basic Auth or Application Passwords are enabled.
    """

    def __init__(self, configuration):
        self.base_url = configuration.wordpress_site_url
        self.username = configuration.wordpress_username
        self.password = configuration.wordpress_app_password

    def get_pages_content(self):

        endpoint = f"{self.base_url}/wp-json/wp/v2/pages"

        response = requests.get(
            endpoint,
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        return response.json()

    def get_wspl_stores(self, per_page=10, page=1):

        endpoint = f"{self.base_url}/wp-json/wp/v2/wpsl_stores"
        params = {'per_page': per_page, 'page': page}

        response = requests.get(
            endpoint,
            params=params,
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        return response.json()

    def get_posts(self, per_page=10, page=1, search=None):
        """
        Fetch a list of posts from WordPress, optionally filtered by a search term.
        """
        endpoint = f"{self.base_url}/wp-json/wp/v2/posts"
        params = {
            "per_page": per_page,
            "page": page,
        }
        if search:
            params["search"] = search  # WP REST API param for searching

        response = requests.get(
            endpoint,
            params=params,
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        return response.json()

    def create_post(self, title, content, status="draft"):
        """
        Create a new WordPress post.
        """
        endpoint = f"{self.base_url}/wp-json/wp/v2/posts"
        data = {
            "title": title,
            "content": content,
            "status": status
        }
        response = requests.post(
            endpoint,
            json=data,
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        return response.json()


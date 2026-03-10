import datetime
import math
import logging
import googlemaps
import requests
from django.utils import timezone
from central_hub.models import TenantConfiguration

logger = logging.getLogger(__name__)

def get_geocode(address, google_maps_api_key):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        'address': address,
        'key': google_maps_api_key
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            formatted_address = data['results'][0]['formatted_address']

            return location, formatted_address
        else:
            print(data)
    return None


def get_address(latitude, longitude, google_maps_api_key):

    gmaps = googlemaps.Client(key=google_maps_api_key)

    # Perform reverse geocoding
    result = gmaps.reverse_geocode((latitude, longitude))

    if not result:
        return None

    # Extract address from the result
    return result[0].get('formatted_address', 'Address not found')


def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Radius of the Earth in kilometers
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = (math.sin(dLat/2) * math.sin(dLat/2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dLon/2) * math.sin(dLon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    return distance


def find_nearby_pois(self, latitude, longitude, google_maps_api_key, radius=500, place_type='restaurant'):
    base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        'location': f'{latitude},{longitude}',
        'radius': radius,
        'type': place_type,
        'key': google_maps_api_key
    }
    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        pois = response.json().get('results', [])
        return pois
    else:
        return []


def find_place(self, name):
    #base_url="https://maps.googleapis.com/maps/api/place/textsearch/json"
    pass

# https://maps.googleapis.com/maps/api/place/findplacefromtext/json?parameters
# https://maps.googleapis.com/maps/api/distancematrix/json?parameters


def calculate_public_transport_eta(origin, destination, google_maps_api_key, print_details=False):
    # Constructing the request URL
    base_url = "https://maps.googleapis.com/maps/api/directions/json?"
    # --------------

    # Get the current date and time in UTC
    current_datetime_utc = timezone.now()

    # Calculate the number of days until the next Monday (0=Monday, 1=Tuesday, ..., 6=Sunday)
    days_until_next_monday = (0 - current_datetime_utc.weekday() + 7) % 7

    # Calculate the next Monday's date
    next_monday_date = current_datetime_utc + datetime.timedelta(days=days_until_next_monday)

    # Set the departure time to 7 AM on the next Monday
    departure_time = next_monday_date.replace(hour=7, minute=0, second=0)

    # Convert departure time to seconds since epoch (January 1, 1970 UTC)
    departure_time_seconds = int(departure_time.timestamp())
    # --------------

    params = {
        "origin": origin,
        "destination": destination,
        "mode": "transit",
        "departure_time": departure_time_seconds,
        "key": google_maps_api_key
    }
    response = requests.get(base_url, params=params)
    directions = response.json()

    # Parsing the response
    if directions["status"] == "OK":

        duration_in_seconds = directions['routes'][0]['legs'][0]['duration']['value']
        duration_in_minutes = duration_in_seconds / 60

        if print_details:

            routes = directions["routes"][0]
            legs = routes["legs"][0]

            # Loop through each step in the legs of the first route
            for step in legs["steps"]:
                if step["travel_mode"] == "WALKING":
                    instructions = step["html_instructions"]
                    distance = step["distance"]["text"]
                    print(f"Walk {distance}: {instructions}")
                elif step["travel_mode"] == "TRANSIT":
                    instructions = step["html_instructions"]
                    departure_stop = step["transit_details"]["departure_stop"]["name"]
                    arrival_stop = step["transit_details"]["arrival_stop"]["name"]
                    line = step["transit_details"]["line"]["short_name"]
                    print(f"Take {line} from {departure_stop} to {arrival_stop}: {instructions}")

        return round(duration_in_minutes,2)
    else:
        return 100000


class GoogleMapsApi:

    def __init__(self, configuration: TenantConfiguration):

        if configuration.google_integration_enabled:
            self.google_maps_api_key = configuration.google_api_key

        else:
            self.google_maps_api_key = None
            raise Exception("Google integration not enabled")

    def get_geocode(self, address):

        if not isinstance(address, str) or not address.strip():
            logger.error("Invalid address: must be a non-empty string")
            return None

        if not isinstance(self.google_maps_api_key, str) or not self.google_maps_api_key.strip():
            logger.error("Invalid API key: must be a non-empty string")
            return None

        # Prepare API request
        url = "https://maps.googleapis.com/maps/api/geocode/json"
        params = {
            'address': address,
            'key': self.google_maps_api_key
        }

        try:
            # Send request with timeout
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()  # Raise exception for 4xx/5xx status codes

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            return None

        try:
            # Parse JSON response
            data = response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            return None

            # Check API status
        if data.get('status') != 'OK':
            logger.warning(f"Geocoding failed with status: {data.get('status', 'Unknown')}")
            return None

        try:
            # Extract location and formatted address
            result = data['results'][0]
            location = result['geometry']['location']
            formatted_address = result['formatted_address']
            return location, formatted_address
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected response structure: {e}")
            return None

    def get_address(self, lat, lng):
        """
        Get a formatted address from latitude and longitude using Google Maps Geocoding API.

        Args:
            lat (float): Latitude coordinate
            lng (float): Longitude coordinate

        Returns:
            str: Formatted address or error message if the request fails
        """
        url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lng}&key={self.google_maps_api_key.strip()}"

        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise an exception for bad status codes
            data = response.json()

            if data["status"] == "OK" and data["results"]:
                # Return the first result's formatted address
                return data["results"][0]["formatted_address"]
            else:
                return "No address found for these coordinates"
        except requests.exceptions.RequestException as e:
            return f"Error fetching address: {str(e)}"

    def search_nearby_places(self, latitude, longitude, place_types: list, radius=500.0, max_results=10):
        url = "https://places.googleapis.com/v1/places:searchNearby"

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.google_maps_api_key,
            "X-Goog-FieldMask": "*"
        }

        payload = {
            "includedTypes": place_types,
            "maxResultCount": max_results,
            "locationRestriction": {
                "circle": {
                    "center": {
                        "latitude": float(latitude),
                        "longitude": float(longitude)
                    },
                    "radius": radius
                }
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()  # Raise an exception for HTTP errors
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}

    def calculate_public_transport_eta(self, origin, destination, print_details=False):
        # Constructing the request URL
        base_url = "https://maps.googleapis.com/maps/api/directions/json?"
        # --------------

        # Get the current date and time in UTC
        current_datetime_utc = timezone.now()

        # Calculate the number of days until the next Monday (0=Monday, 1=Tuesday, ..., 6=Sunday)
        days_until_next_monday = (0 - current_datetime_utc.weekday() + 7) % 7

        # Calculate the next Monday's date
        next_monday_date = current_datetime_utc + datetime.timedelta(days=days_until_next_monday)

        # Set the departure time to 7 AM on the next Monday
        departure_time = next_monday_date.replace(hour=7, minute=0, second=0)

        # Convert departure time to seconds since epoch (January 1, 1970 UTC)
        departure_time_seconds = int(departure_time.timestamp())
        # --------------

        params = {
            "origin": origin,
            "destination": destination,
            "mode": "transit",
            "departure_time": departure_time_seconds,
            "key": self.google_maps_api_key
        }
        response = requests.get(base_url, params=params)
        directions = response.json()

        # Parsing the response
        if directions["status"] == "OK":

            duration_in_seconds = directions['routes'][0]['legs'][0]['duration']['value']
            duration_in_minutes = duration_in_seconds / 60

            if print_details:

                routes = directions["routes"][0]
                legs = routes["legs"][0]

                # Loop through each step in the legs of the first route
                for step in legs["steps"]:
                    if step["travel_mode"] == "WALKING":
                        instructions = step["html_instructions"]
                        distance = step["distance"]["text"]
                        print(f"Walk {distance}: {instructions}")
                    elif step["travel_mode"] == "TRANSIT":
                        instructions = step["html_instructions"]
                        departure_stop = step["transit_details"]["departure_stop"]["name"]
                        arrival_stop = step["transit_details"]["arrival_stop"]["name"]
                        line = step["transit_details"]["line"]["short_name"]
                        print(f"Take {line} from {departure_stop} to {arrival_stop}: {instructions}")

            return round(duration_in_minutes, 2)
        else:
            return 100000

    def find_nearby_pois(self, latitude, longitude, radius=500, place_type='restaurant'):
        base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            'location': f'{latitude},{longitude}',
            'radius': radius,
            'type': place_type,
            'key': self.google_maps_api_key
        }
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            pois = response.json().get('results', [])
            return pois
        else:
            return []
from portal.models import TenantConfiguration, Tenant
from moio_platform.lib.google_maps_api import GoogleMapsApi, haversine
from moio_platform.lib.wordpress_api import WordPressAPIClient

config = TenantConfiguration.objects.get(tenant_id=16)
maps = GoogleMapsApi(config)

location = maps.get_geocode("Biarritz 7271, montevideo")
print(location)

# pois = maps.search_nearby_places(location[0]["lat"], location[0]["lng"], place_types=[])
# pois = maps.find_nearby_pois(location[0]["lat"], location[0]["lng"],place_type=["gas_station"])
# print(pois)


wp = WordPressAPIClient(config)
stores = wp.get_wspl_stores(per_page=100)
recommended_stores = []

for store in stores:

    address_info = store["location_info"]

    distance = haversine(float(location[0]["lat"]), float(location[0]["lng"]), float(address_info["latitude"]), float(address_info["longitude"]))

    loc = {
        "name": store["title"]["rendered"],
        "category": store["wpsl_store_category"],
        "address": address_info["address"],
        "city": address_info["city"],
        "work_hours": address_info["work_hours"],
        "phone": address_info["phone"],
        "email": address_info["email"],
        "email:": address_info["email"],
        "url": address_info["url"],
        "distance": round(distance,0)
    }

    recommended_stores.append(loc)

sorted_places = sorted(recommended_stores, key=lambda item: item["distance"])

for sp in sorted_places:
    print(sp)

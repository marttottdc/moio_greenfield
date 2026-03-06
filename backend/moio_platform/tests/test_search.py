from django.contrib.postgres.search import SearchVector

from crm.models import Tag, Product
from moio_platform.lib.openai_gpt_api import MoioOpenai
from portal.models import TenantConfiguration
from moio_platform.lib.moio_assistant_functions import MoioAssistantTools
from pgvector.django import L2Distance, CosineDistance
from crm.lib.crm_search import search_text, search_by_product, search_by_tag

config = TenantConfiguration.objects.get(tenant_id__exact=16)
mo = MoioOpenai(config.openai_api_key, config.openai_default_model)


while True:

    search_term = input('Search term: ')
    matches = search_by_tag(search_term)
    print(matches)
    matches_p = search_by_product(search_term)
    print(matches_p)
    matches_ts = search_text(search_term)
    print(matches_ts)
    """
    print('Possible Matches')
    if matches.count() > 0:
        matches_list = []
        i = 1

        for match in matches:
            print(f'{i}: {match.name} -  {match.l2_distance} - {match.cos_distance}')
            matches_list.append(match)
            i += 1
        print("-----------------------------------------------------------------------")
        print("0: Ninguno de esos")
        user_choice = input('Selecciona el modelo más parecido:')

        prods = Product.objects.filter(tags__name=matches_list[int(user_choice)-1]).distinct()
        for prod in prods:
            print(prod.name, prod.brand, prod.permalink)
        """
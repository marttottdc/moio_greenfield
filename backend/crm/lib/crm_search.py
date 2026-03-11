from django.contrib.postgres.search import SearchVector

from crm.models import Tag, Product
from moio_platform.lib.openai_gpt_api import MoioOpenai
from pgvector.django import L2Distance, CosineDistance


def search_by_tag(search_term, config):

    search_term = search_term.lower()
    search_term_embedding = mo.get_embedding(search_term)

    matches = Tag.objects.filter(tenant=config.tenant).order_by(
        L2Distance('embedding', search_term_embedding)).annotate(
        l2_distance=L2Distance('embedding', search_term_embedding),
        cos_distance=CosineDistance('embedding', search_term_embedding)).filter(l2_distance__lt=1.2)[:5]

    return matches


def search_by_product(search_term):

    search_term = search_term.lower()
    search_term_embedding = mo.get_embedding(search_term)

    matches = Product.objects.filter(tenant=config.tenant).order_by(
        L2Distance('embedding', search_term_embedding)).annotate(
        l2_distance=L2Distance('embedding', search_term_embedding),
        cos_distance=CosineDistance('embedding', search_term_embedding)).filter(l2_distance__lt=1.2)[:5]

    return matches


def search_text(search_term):

    products = Product.objects.annotate(
        search_vector=SearchVector('name', 'description', 'tags')
    ).filter(search_vector=search_term)

    print(f'Resultados para productos: {products}')

    tags = Tag.objects.annotate(
        search_vector=SearchVector('name', 'description', 'context')
    ).filter(search_vector=search_term).distinct()

    print(f'Resultados para tags: {tags}')

    return list(products)+list(tags)



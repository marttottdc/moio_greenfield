# Importing required modules
from django.urls import URLPattern, URLResolver

from moio_platform.urls import urlpatterns as app_urls
from moio_platform.urls import urlpatterns as project_urls


def list_urls(urlpatterns, prefix=''):
    for urlpattern in urlpatterns:
        if isinstance(urlpattern, URLResolver):  # If the pattern is a resolver (includes other patterns)
            list_urls(urlpattern.url_patterns, prefix + urlpattern.pattern.regex.pattern)
        elif isinstance(urlpattern, URLPattern):  # If the pattern is a URL pattern
            print(prefix + urlpattern.pattern.regex.pattern)


# Listing project-level URLs
print("Project-level URLs:")
list_urls(project_urls)

# Listing app-level URLs
print("\nApp-level URLs:")
list_urls(app_urls)
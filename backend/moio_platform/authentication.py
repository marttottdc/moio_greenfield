from rest_framework.authentication import TokenAuthentication


class BearerTokenAuthentication(TokenAuthentication):
    """Token authentication that expects a Bearer keyword."""

    keyword = "Bearer"

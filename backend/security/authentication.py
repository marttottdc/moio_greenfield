import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ServiceJWTAuthentication(BaseAuthentication):
    """
    JWT authentication for service-to-service requests.
    Validates tokens signed with SERVICE_TOKEN_SECRET.
    """

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header.startswith('Bearer '):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        try:
            payload = jwt.decode(token,
                                 settings.SERVICE_TOKEN_SECRET,
                                 algorithms=["HS256"],
                                 audience="moio_platform",
                                 leeway=30)
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f'Invalid token: {str(e)}')

        # Return a dummy user object with token payload attached
        # This allows permission classes to access the payload
        class ServiceUser:
            is_authenticated = True

            def __str__(self):
                return payload.get('iss', 'service')

        user = ServiceUser()
        return (user, payload)

    def authenticate_header(self, request):
        return 'Bearer realm="api"'

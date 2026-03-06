from rest_framework.permissions import BasePermission


class RequireServiceScope(BasePermission):
    """
    Permission class that checks if service token has required scope.
    
    Usage in view:
        class MyView(APIView):
            permission_classes = [RequireServiceScope]
            required_scope = "pages.read"
    """
    required_scope = None

    def has_permission(self, request, view):
        # request.auth contains the JWT payload from ServiceJWTAuthentication
        if not request.auth:
            return False

        scopes = request.auth.get('scopes', [])
        
        # Check if view has a required_scope
        required = getattr(view, 'required_scope', None) or self.required_scope
        if not required:
            # No scope requirement specified
            return True

        return required in scopes

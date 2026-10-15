from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from drf_spectacular.utils import extend_schema
from rest_framework import status

from base.decorators import extend_response
from base.exceptions import SerializerError
from base.types import DefaultSuccessResponseType
from base.views import BaseAV
from modules.core.api.v1.serializers import (
    CsrfSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)


class CsrfAV(BaseAV):
    "Issue a CSRF token (and cookie). Send it as X-CSRFToken on authenticated writes."

    authentication = False

    @extend_response(CsrfSerializer())
    def get(self, request):
        return {"csrf_token": get_token(request)}


class RegisterAV(BaseAV):
    "Sign up with name, email and password; signs the new user in."

    authentication = {"post": False}

    @extend_schema(request=RegisterSerializer)
    @extend_response(UserSerializer())
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            raise SerializerError(serializer.errors)
        user = serializer.save()
        login(request, user)
        return UserSerializer(instance=user).data


class LoginAV(BaseAV):
    "Current user (GET), sign in (POST), sign out (DELETE)."

    authentication = {"post": False, "delete": False}

    @extend_response(UserSerializer())
    def get(self, request):
        return UserSerializer(instance=request.user).data

    @extend_schema(request=LoginSerializer)
    @extend_response(UserSerializer())
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            raise SerializerError(serializer.errors)
        user = authenticate(
            request,
            email=serializer.validated_data["email"].lower(),
            password=serializer.validated_data["password"],
        )
        if user is None:
            self.fail("Email or password is incorrect.", status.HTTP_401_UNAUTHORIZED)
        login(request, user)
        return UserSerializer(instance=user).data

    @extend_response(DefaultSuccessResponseType)
    def delete(self, request):
        logout(request)
        return self.success("Signed out.")

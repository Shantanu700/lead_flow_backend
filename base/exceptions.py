from django.core import exceptions
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import set_rollback


def exception_handler(exc, context):
    if isinstance(exc, exceptions.ValidationError):
        data = {"msg": exc.error_list}
        return Response(data, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, APIException):
        headers = {}
        if getattr(exc, "auth_header", None):
            headers["WWW-Authenticate"] = exc.auth_header # type: ignore
        if getattr(exc, "wait", None):
            headers["Retry-After"] = "%d" % exc.wait # type: ignore

        if isinstance(exc.detail, (list, dict)):
            data = exc.detail
        else:
            data = {"msg": exc.detail}

        set_rollback()
        return Response(data, status=exc.status_code, headers=headers)

    return None


class PermissionException(APIException):

    def __init__(self, detail=None, code=None):
        super().__init__(detail, code)
        self.status_code = code


class CustomError(APIException):
    "A request the server refuses, with a message to show the user (400 unless given)."
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, detail=None, code=None, status_code=None):
        super().__init__(detail, code)
        if status_code:
            self.status_code = status_code


class SerializerError(APIException):
    "Invalid input: the serializer's errors per field (400)."
    status_code = status.HTTP_400_BAD_REQUEST

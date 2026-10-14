from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from base.serializers import BaseSerializer
from modules.core.models import User


class UserSerializer(BaseSerializer):
    class Meta:
        model = User
        fields = ("id", "uuid", "name", "email")


class RegisterSerializer(BaseSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    email = serializers.EmailField()

    class Meta:
        model = User
        fields = ("name", "email", "password")
        extra_kwargs = {"name": {"required": True, "allow_blank": False}}

    def validate_email(self, value):
        value = value.lower()
        if User.unfiltered_objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        # Run Django's validators against the would-be user so the similarity
        # check can compare the password with the name and email.
        candidate = User(email=attrs.get("email", ""), name=attrs.get("name", ""))
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()

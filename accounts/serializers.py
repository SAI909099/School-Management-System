from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from .models import User

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'phone', 'first_name', 'last_name', 'role')

class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=4)

    class Meta:
        model = User
        fields = ('id', 'phone', 'first_name', 'last_name', 'role', 'password')

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)
        user.set_password(password)
        user.save()
        return user

class PhoneTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        return token

    def _normalize_phone(self, s: str) -> str:
        if not s:
            return s
        # keep only + and digits, remove spaces/dashes/etc.
        import re
        s = re.sub(r'[^\d+]', '', s)
        # if it starts with country code without + but you always store with +, add it:
        # (optional; comment out if you store without +)
        if s and not s.startswith('+') and s.startswith('998'):
            s = '+' + s
        return s

    def validate(self, attrs):
        # Accept either 'phone' or 'username' (forms sometimes send username)
        phone = attrs.get('phone') or attrs.get('username')
        if phone:
            phone = self._normalize_phone(phone)
            # Ensure the serializer puts the normalized value under the correct key
            attrs[self.username_field] = phone
        return super().validate(attrs)

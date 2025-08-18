from rest_framework import serializers

from resident.serializers.base import BaseSerializer


class MembershipSearch(BaseSerializer):
    
    key = serializers.CharField(
        required=False,
        max_length=150,
        allow_blank=True,
    )
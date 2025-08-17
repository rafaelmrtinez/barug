from rest_framework import serializers

from resident.serializers.base import BaseSerializer


class FamilySelectionSerializer(BaseSerializer):

    household_id = serializers.IntegerField(
        required=True,
        error_messages={
            'required': "Household ID is required.",
            'blank': "Household ID cannot be blank.",
            'invalid': "Invalid Household ID."
        }
    )

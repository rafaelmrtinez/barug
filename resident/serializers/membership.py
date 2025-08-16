from rest_framework import serializers

class MembershipSerializer(serializers.Serializer):
    resident_id = serializers.IntegerField(
        required=True,
        help_text="The ID of the resident",
        error_messages={
            "required": "Resident ID is required."
        }
    )
    household_id = serializers.IntegerField(
        required=True,
        help_text="Household id of specific household",
        error_messages={
            "required": "Household ID is required."
        }
    )
    family_id = serializers.IntegerField(
        required=True,
        help_text="Family id of specific family",
        error_messages={
            "required": "Family ID is required."
        }
    )
    household_head_relationship = serializers.IntegerField(
        required=True,
        help_text="Household head relationship",
        error_messages={
            "required": "Household head relationship is required."
        }
    )
    family_head_relationship = serializers.IntegerField(
        required=True,
        help_text="Family head relationship",
        error_messages={
            "required": "Family head relationship is required."
        }
    )

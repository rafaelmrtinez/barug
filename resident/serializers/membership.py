from rest_framework import serializers


class MembershipSerializer(serializers.Serializer):

    household_id = serializers.IntegerField(
        required=True,
        error_messages={
            "invalid": "Invalid Household ID. Please try again.",
            "required": "Household ID is required."
        }
    )
    family_id = serializers.IntegerField(
        required=True,
        error_messages={
            "invalid": "Invalid Family ID. Please try again.",
            "required": "Family ID is required."
        }
    )
    household_head_relationship = serializers.IntegerField(
        required=True,
        error_messages={
            "invalid": "Please select correct relationship for Household Head (e.g., Father, Mother).",
            "required": "Household head relationship is required."
        }
    )
    family_head_relationship = serializers.IntegerField(
        required=True,
        error_messages={
            "invalid": "Please select correct relationship for Family Head (e.g., Father, Mother).",
            "required": "Family head relationship is required."
        }
    )
    resident_id = serializers.IntegerField(
        required=True,
        error_messages={
            "invalid": "",
            "required": ""
        }
    )
    username = serializers.CharField(
        required=True,
        max_length=150,
        error_messages={
            "invalid": "",
            "blank": "",
            "max_length": "",
            "required": ""
        }
    )
    role = serializers.CharField(
        required=True,
        max_length=100,
        error_messages={
            "invalid": "",
            "blank": "",
            "max_length": "",
            "required": ""
        }
    )

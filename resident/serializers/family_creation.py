from rest_framework import serializers

class FamilyCreationSerializer(serializers.Serializer):
    
    requester_id = serializers.CharField(
        required=True,
        error_messages={
            "required": "Requester ID is required.",
            "invalid": "Invalid requester ID provided."
        }
    )
    indigent_status = serializers.IntegerField(
        required=True,
        error_messages={
            "required": "Indigent status is required.",
            "invalid": "Invalid indigent status value."
        }
    )
    household_number = serializers.CharField(
        required=True,
        error_messages={
            "required": "Household number is required.",
            "invalid": "Invalid household number provided."
        }
    )
    source_of_income = serializers.CharField(
        required=True,
        error_messages={
            "required": "Source of income is required.",
            "invalid": "Invalid source of income provided."
        }
    )
    family_monthly_income = serializers.IntegerField(
        required=True,
        error_messages={
            "required": "Family monthly income is required.",
            "invalid": "Invalid family monthly income value."
        }
    )
    household_head_relationship = serializers.IntegerField(
        required=True,
        error_messages={
            "required": "Household head relationship is required.",
            "invalid": "Invalid household head relationship value."
        }
    )

    nhts_status = serializers.IntegerField(
        required=True,
        error_messages={
            "required": "NHTS status is required.",
            "invalid": "Invalid NHTS status value."
        }
    )
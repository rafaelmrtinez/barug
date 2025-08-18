from rest_framework import serializers

class BaseSerializer(serializers.Serializer):

    class Meta:
        abstract = True
        fields = ['resident_id', 'username', 'role']

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
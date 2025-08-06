from rest_framework import serializers

class FAQDocumentSerializer(serializers.Serializer):
    """
    Serializer for FAQ document ingestion requests.
    """
    file = serializers.FileField(
        required=True,
        help_text="The Excel file containing FAQs to be ingested.",
        allow_empty_file=False
    )
    
    created_at = serializers.DateTimeField(
        required=True,
        help_text="The timestamp when the document is created.",
        format="%Y-%m-%dT%H:%M:%S.%fZ",
        input_formats=["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%S"]
    )
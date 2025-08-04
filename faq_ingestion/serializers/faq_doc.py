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
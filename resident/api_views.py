from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from .serializers import ResidentSerializer
from .models import Resident
from supabase_client import supabase

class ResidentRegisterAPIView(APIView):
    def post(self, request):
        # Save data to Supabase DB via Django ORM
        serializer = ResidentSerializer(data=request.data)
        if serializer.is_valid():
            resident = serializer.save()

            # Upload file to Supabase Storage
            file = request.FILES.get("id_photo")
            if file:
                file_path = f"residents/{resident.id}/{file.name}"
                supabase.storage.from_("residents-photos").upload(file_path, file)
                resident.id_photo_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/residents-photos/{file_path}"
                resident.save()

            return Response({"message": "Resident created successfully."}, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

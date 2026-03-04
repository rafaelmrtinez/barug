from django.shortcuts import redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.db import connection, transaction
from django.conf import settings
from authentication.guards import session_login_required, role_required
import uuid
import os

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
@require_POST
def upload_scanned_copy(request, case_id: int):
    """Upload scanned copies (final copy, settlement copy, etc.) for a case."""
    document_type = (request.POST.get('document_type') or 'FINAL_COPY').strip()
    staff_id = (request.session.get('auth') or {}).get('staff_id')
    
    files = request.FILES.getlist('file_0') or request.FILES.getlist('file')
    if not files:
        # Collect all uploaded files
        files = []
        i = 0
        while f'file_{i}' in request.FILES:
            files.extend(request.FILES.getlist(f'file_{i}'))
            i += 1
    
    if not files:
        return JsonResponse({'success': False, 'error': 'No files uploaded'})
    
    bucket = getattr(settings, 'SUPABASE_BUCKET', 'documents')
    saved_count = 0
    
    try:
        from common.supabase_client import supabase
        
        with transaction.atomic():
            with connection.cursor() as cur:
                for file in files:
                    if not file:
                        continue
                    
                    # Generate unique filename
                    ext = os.path.splitext(file.name)[1] or '.bin'
                    unique_name = f"{uuid.uuid4().hex}{ext}"
                    file_path = f"case_documents/{case_id}/{unique_name}"
                    
                    # Upload to Supabase
                    try:
                        supabase.storage.from_(bucket).upload(
                            file_path,
                            file.read(),
                            {'contentType': file.content_type or 'application/octet-stream', 'upsert': 'true'}
                        )
                        
                        # Get public URL
                        storage_url = None
                        try:
                            pub = supabase.storage.from_(bucket).get_public_url(file_path)
                            storage_url = pub.get('publicUrl') if isinstance(pub, dict) else (pub if isinstance(pub, str) else None)
                        except:
                            pass
                        
                        if not storage_url:
                            try:
                                signed = supabase.storage.from_(bucket).create_signed_url(file_path, 60*60*24*7)
                                storage_url = signed.get('signedURL') or signed.get('signedUrl') or signed.get('signed_url')
                            except:
                                pass
                        
                        # Store in database
                        cur.execute("""
                            INSERT INTO case_document 
                            (blotter_case_id, document_type, file_name, file_path, mime_type, file_size_bytes, uploaded_by_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, [
                            case_id,
                            document_type,
                            file.name,
                            storage_url or file_path,
                            file.content_type,
                            file.size,
                            staff_id
                        ])
                        saved_count += 1
                    except Exception as e:
                        print(f"Error uploading file {file.name}: {e}")
                        continue
        
        if saved_count > 0:
            return JsonResponse({'success': True, 'message': f'Uploaded {saved_count} file(s)'})
        else:
            return JsonResponse({'success': False, 'error': 'No files were successfully uploaded'})
    
    except Exception as e:
        print(f"Error in upload_scanned_copy: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

from authentication.supabase_client import supabase
from django.conf import settings
import mimetypes
import logging


class SupabaseStorageService:

    @staticmethod
    def save_file(file, destination_path, bucket_name):
        """Upload bytes or file-like to Supabase storage.

        Ensures the payload is bytes, sets a sensible Content-Type when available,
        and returns a normalized dict: {"path", "public_url", "raw"}.
        Treats 409 (Duplicate) as success and returns the public URL for the path.
        """
        try:
            # read bytes if a file-like object
            data = file
            content_type = None
            # Django's UploadedFile exposes .read() and .content_type
            if hasattr(file, 'read'):
                try:
                    data = file.read()
                except Exception:
                    # fallback to attribute 'file' if present
                    data = getattr(file, 'file', file)
                # try to get content_type from the uploaded file
                content_type = getattr(file, 'content_type', None)

            # if data is a str, encode to bytes
            if isinstance(data, str):
                data = data.encode('utf-8')

            # convert memoryview to bytes
            try:
                if isinstance(data, memoryview):
                    data = data.tobytes()
            except Exception:
                pass

            # if content_type missing, try to guess from filename
            if not content_type:
                try:
                    name = getattr(file, 'name', None) or destination_path
                    content_type, _ = mimetypes.guess_type(name)
                except Exception:
                    content_type = None

            options = {}
            if content_type:
                options['content-type'] = content_type

            # call upload (some clients accept options dict as third arg)
            try:
                raw = supabase.storage.from_(bucket_name).upload(destination_path, data, options)
            except TypeError:
                # fallback: call without options if client signature differs
                raw = supabase.storage.from_(bucket_name).upload(destination_path, data)

            # Normalize response
            error = None
            status_code = None
            if isinstance(raw, dict):
                error = raw.get('error') or raw.get('message')
                status_code = raw.get('statusCode') or raw.get('status_code') or raw.get('status')
            else:
                error = getattr(raw, 'error', None)
                status_code = getattr(raw, 'status_code', None)

            # if error present, handle duplicates specially
            if error:
                # try to extract status from raw error
                try:
                    first = error if not isinstance(error, dict) else error
                    # StorageApiError from storage3 often raises a dict as first arg; handled below
                except Exception:
                    pass

            # if we have a status code and it's an error that's not 409, raise
            try:
                if status_code and int(status_code) >= 400 and int(status_code) != 409:
                    raise Exception(f"Error uploading file: status {status_code}")
            except Exception:
                # ignore parsing issues and fallthrough to return
                pass

            # Build public URL when SUPABASE_URL is configured
            supabase_url = getattr(settings, 'SUPABASE_URL', None)
            public_url = None
            if supabase_url:
                public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket_name}/{destination_path}"

            return {"path": destination_path, "public_url": public_url, "raw": raw}

        except Exception as e:
            # if the storage client included a dict-like first arg with a statusCode, treat 409 as success
            try:
                first = e.args[0] if e.args else None
                if isinstance(first, dict) and int(first.get('statusCode', 0)) == 409:
                    supabase_url = getattr(settings, 'SUPABASE_URL', None)
                    public_url = None
                    if supabase_url:
                        public_url = f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket_name}/{destination_path}"
                    return {"path": destination_path, "public_url": public_url, "raw": first}
            except Exception:
                pass

            raise Exception(f"Failed to upload file: {str(e)}")

    @staticmethod
    def remove_file(destination_path, bucket_name):
        """Remove a single object from the given bucket. Returns True on success.

        Uses the supabase client remove API which accepts a list of object paths.
        """
        try:
            logger = logging.getLogger(__name__)
            # the client expects a list of paths
            logger.debug('Supabase remove_file called for bucket=%s path=%s', bucket_name, destination_path)
            res = supabase.storage.from_(bucket_name).remove([destination_path])
            # log response when available (some clients return dict-like)
            try:
                logger.debug('Supabase remove response for %s: %s', destination_path, res)
            except Exception:
                pass
            # some clients return dict/error shape; treat any non-exception as success
            return True
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.exception('Supabase remove_file failed for bucket=%s path=%s', bucket_name, destination_path)
            # bubble up the exception to let callers decide what to do
            raise
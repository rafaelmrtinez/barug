import base64
from typing import Optional
import requests


class FAQIngestionGateway:
    """Repository responsible for sending FAQ Excel files to the upstream
    Supabase function endpoint.

    The repository provides a JSON-based upload method (encodes the file as
    base64) which matches the function contract described in the task.
    """

    def __init__(self, endpoint_url: Optional[str] = None, timeout: int = 60):
        # default endpoint can be passed explicitly or left as the project one
        self.endpoint = endpoint_url or "https://ucvhvzimwtkrilyyhffc.supabase.co/functions/v1/upload-api"
        self.timeout = timeout

    def upload_via_json(self, file_bytes: bytes, filename: str, uploaded_by: str) -> dict:
        """Upload the file by encoding it as base64 and posting JSON.

        Returns the decoded JSON response on success. Raises requests.HTTPError
        on non-2xx responses.
        """
        encoded = base64.b64encode(file_bytes).decode("ascii")
        payload = {
            "fileName": filename,
            "fileData": encoded,
            "uploaded_by": uploaded_by,
        }

        resp = requests.post(self.endpoint, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "http_status": resp.status_code}

    def upload_multipart(self, file_bytes: bytes, filename: str, uploaded_by: str) -> dict:
        """Alternative using multipart/form-data (falls back to JSON endpoint if needed).

        This posts the file directly as form data. Returns JSON-decoded response.
        """
        files = {"file": (filename, file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        data = {"uploaded_by": uploaded_by}
        resp = requests.post(self.endpoint, files=files, data=data, timeout=self.timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "http_status": resp.status_code}

    def get_faqs(self, version: str = "1") -> dict:
        """Retrieve FAQs from the upstream edge function via GET.

        The edge function follows the pattern: /functions/v{version}/faqs-api
        Returns the decoded JSON response as a dict. Raises requests.HTTPError
        on non-2xx responses.
        """
        # construct endpoint replacing the function name and version
        base = self.endpoint
        # attempt to derive base domain if endpoint points to a different function
        # e.g. https://.../functions/v1/upload-api -> https://.../functions/v{version}/faqs-api
        try:
            # split at '/functions/' and rebuild
            parts = base.split('/functions/')
            if len(parts) == 2:
                domain = parts[0]
                endpoint = f"{domain}/functions/v{version}/faqs-api"
            else:
                # fallback: replace upload-api with faqs-api
                endpoint = base.replace('upload-api', 'faqs-api')
        except Exception:
            endpoint = base.replace('upload-api', 'faqs-api')

        resp = requests.get(endpoint, timeout=self.timeout)
        resp.raise_for_status()
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "http_status": resp.status_code}
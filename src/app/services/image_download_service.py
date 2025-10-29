import io
import logging
import os
import zipfile
from typing import Tuple, List

import requests
from django.conf import settings

from maternal.supa.supabase_storage_service import SupabaseStorageService


logger = logging.getLogger(__name__)


class ImageDownloadService:
    """Service to collect laboratory image files for a maternal record and
    return a ZIP archive bytes object.

    Behaviour:
      - Uses repository.fetch_lab_results_by_mhr_id(mhr_id) to locate lab rows.
      - Each row's `result_img_path` may be a JSON/list or a single string.
      - For each image path/URL the service will attempt to fetch bytes. If the
        image string looks like a full URL (starts with http) it will be
        requested directly. Otherwise a public URL for the Supabase storage
        bucket will be constructed using settings.SUPABASE_URL and fetched.
      - Collected files are added to an in-memory ZIP and returned as bytes.
    """

    def __init__(self, repository, bucket_name: str = 'maternal') -> None:
        self.repository = repository
        self.bucket = bucket_name

    def _collect_image_urls(self, mhr_id: int) -> List[Tuple[str, str]]:
        """Return list of tuples (fetch_url, filename) for images attached to mhr.

        Attempts to normalise storage paths into public URLs when possible.
        """
        rows = self.repository.fetch_lab_results_by_mhr_id(mhr_id) or []
        urls = []
        supabase_url = getattr(settings, 'SUPABASE_URL', '').rstrip('/') if getattr(settings, 'SUPABASE_URL', None) else ''

        for r in rows:
            raw_imgs = r.get('result_img_path')
            imgs_list = []
            if not raw_imgs:
                continue
            if isinstance(raw_imgs, str):
                try:
                    import json
                    imgs_list = json.loads(raw_imgs)
                except Exception:
                    imgs_list = [raw_imgs]
            elif isinstance(raw_imgs, (list, tuple)):
                imgs_list = list(raw_imgs)
            else:
                try:
                    imgs_list = list(raw_imgs)
                except Exception:
                    continue

            for img in imgs_list:
                try:
                    s = str(img)
                    if s.lower().startswith('http'):
                        fetch_url = s
                        filename = os.path.basename(fetch_url.split('?')[0]) or f'image-{len(urls)}'
                    else:
                        # construct public URL for Supabase storage public objects
                        if supabase_url:
                            fetch_url = f"{supabase_url}/storage/v1/object/public/{self.bucket}/{s}"
                        else:
                            # fallback: treat the stored value as a path and try to fetch it directly
                            fetch_url = s
                        filename = os.path.basename(s.split('?')[0]) or f'image-{len(urls)}'
                    urls.append((fetch_url, filename))
                except Exception:
                    logger.exception('Failed to normalise image entry: %s', img)
                    continue

        return urls

    def zip_lab_images_for_maternal_record(self, mhr_id: int) -> Tuple[bytes, str]:
        """Fetch images for the given maternal record id and return (zip_bytes, filename).

        Raises ValueError when no images are found, or Exception on unexpected failures.
        """
        urls = self._collect_image_urls(mhr_id)
        if not urls:
            raise ValueError('No images found for this maternal record.')

        bio = io.BytesIO()
        # use ZIP_DEFLATED when available
        try:
            zf = zipfile.ZipFile(bio, mode='w', compression=zipfile.ZIP_DEFLATED)
        except Exception:
            zf = zipfile.ZipFile(bio, mode='w')

        session = requests.Session()
        # set a short timeout for each request
        timeout = 30

        for fetch_url, filename in urls:
            try:
                resp = session.get(fetch_url, timeout=timeout, stream=True)
                if resp.status_code == 200:
                    # read content in chunks and write into an in-memory buffer
                    content = resp.content
                    # Ensure filenames are unique within the zip
                    unique_name = filename
                    idx = 1
                    while unique_name in zf.namelist():
                        name_root, ext = os.path.splitext(filename)
                        unique_name = f"{name_root}-{idx}{ext}"
                        idx += 1
                    zf.writestr(unique_name, content)
                else:
                    logger.warning('Failed to fetch %s (status=%s); skipping', fetch_url, resp.status_code)
            except Exception:
                logger.exception('Error fetching image %s; skipping', fetch_url)
                continue

        zf.close()
        bio.seek(0)
        zip_bytes = bio.read()
        zip_name = f'mhr_{mhr_id}_lab_images.zip'
        return zip_bytes, zip_name

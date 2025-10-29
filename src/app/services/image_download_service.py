import io
import logging
import os
import zipfile
import tempfile
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
        """Return list of tuples (fetch_url, filename, folder) for images attached to mhr.

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
                    # determine folder name for this lab row so files are grouped
                    lab_name = None
                    try:
                        lab_name = r.get('lab_test_type_name') or r.get('lab_test_name') or r.get('lab_test') or r.get('lab_test_id')
                    except Exception:
                        lab_name = None
                    # sanitize folder name
                    folder = str(lab_name) if lab_name is not None else 'unknown_test'
                    # replace problematic chars
                    folder = folder.strip()
                    # keep only safe characters
                    import re
                    folder = re.sub(r'[^A-Za-z0-9 _-]', '_', folder)
                    folder = folder.replace(' ', '_') or 'unknown_test'

                    urls.append((fetch_url, filename, folder))
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

        # For large downloads we stream files to a temporary zip on disk to
        # avoid building the entire archive in memory. We'll download each
        # image into a temporary file, add it to the zip under the
        # folder/<filename> path, then remove the temporary file.
        session = requests.Session()
        timeout = 30

        tmp = tempfile.NamedTemporaryFile(prefix=f'mhr_{mhr_id}_', suffix='.zip', delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            # create zip file on disk
            try:
                zf = zipfile.ZipFile(tmp_path, mode='w', compression=zipfile.ZIP_DEFLATED)
            except Exception:
                zf = zipfile.ZipFile(tmp_path, mode='w')

            for fetch_url, filename, folder in urls:
                try:
                    resp = session.get(fetch_url, timeout=timeout, stream=True)
                    if resp.status_code == 200:
                        # write response to temporary file to avoid using memory
                        img_tmp = tempfile.NamedTemporaryFile(prefix='img_', delete=False)
                        img_path = img_tmp.name
                        try:
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:
                                    img_tmp.write(chunk)
                            img_tmp.flush()
                        finally:
                            img_tmp.close()

                        # ensure unique arcname within folder
                        base_name = filename
                        name_root, ext = os.path.splitext(base_name)
                        candidate = f"{folder}/{base_name}"
                        idx = 1
                        existing = set([n for n in zf.namelist() if n.startswith(folder + '/')])
                        while candidate in existing:
                            base_name = f"{name_root}-{idx}{ext}"
                            candidate = f"{folder}/{base_name}"
                            idx += 1
                        zf.write(img_path, arcname=candidate)
                        # remove the image temp file
                        try:
                            os.remove(img_path)
                        except Exception:
                            logger.debug('Failed to remove temp image file %s', img_path)
                    else:
                        logger.warning('Failed to fetch %s (status=%s); skipping', fetch_url, resp.status_code)
                except Exception:
                    logger.exception('Error fetching image %s; skipping', fetch_url)
                    continue

            zf.close()
            zip_name = f'mhr_{mhr_id}_lab_images.zip'
            return tmp_path, zip_name
        except Exception:
            # cleanup on error
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

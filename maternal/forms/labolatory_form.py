# maternal/forms/laboratory_form.py
import json
import logging
from decimal import Decimal
from typing import Any, Dict, List

from django import forms
from django.core.exceptions import ValidationError


from maternal.forms.maternal_identification_form import add_bootstrap_classes
from maternal.forms.widgets import MultiImageInput
from src.infra.repositories.maternal_health_record_repository import MaternalHealthRecordRepository
# Note: form is responsible for form-related presentation logic (initials,
# readonly flags, image-preview data). Repository lookups are allowed here to
# populate the form; business rules for persistence remain in the service.


class LaboratoryForm(forms.Form):
    # --- Results ---
    urinalysis       = forms.CharField(required=False, label="Urinalysis")
    cbc              = forms.CharField(required=False, label="CBC")
    sgot_sgpt        = forms.CharField(required=False, label="SGOT/SGPT")
    creatinine_serum = forms.CharField(required=False, label="Creatinine serum")
    bua_bun          = forms.CharField(required=False, label="BUA/BUN")
    syphilis         = forms.CharField(required=False, label="Syphilis")
    hiv_test         = forms.CharField(required=False, label="HIV test")
    hepa_b           = forms.CharField(required=False, label="HEPA B")
    blood_typing     = forms.CharField(required=False, label="Blood typing")
    ogct_50g         = forms.DecimalField(required=False, label="OGCT (50g, 24–28 wks) mg/dL", max_digits=6, decimal_places=2)

    # --- Dates ---
    urinalysis_date       = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    cbc_date              = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    sgot_sgpt_date        = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    creatinine_serum_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    bua_bun_date          = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    syphilis_date         = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hiv_test_date         = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    hepa_b_date           = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    blood_typing_date     = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    ogct_50g_date         = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))

    # --- Attachments (multi-image per test) ---
    img_widget = MultiImageInput(attrs={"multiple": True, "accept": "image/*"})

    # Render multi-file inputs but avoid FileField/ImageField validation here.
    # The view will read actual files from request.FILES (attached to the form as
    # `form._raw_files`) and our helpers will process them.
    urinalysis_images       = forms.CharField(required=False, widget=img_widget, label="Attachments")
    cbc_images              = forms.CharField(required=False, widget=img_widget, label="Attachments")
    sgot_sgpt_images        = forms.CharField(required=False, widget=img_widget, label="Attachments")
    creatinine_serum_images = forms.CharField(required=False, widget=img_widget, label="Attachments")
    bua_bun_images          = forms.CharField(required=False, widget=img_widget, label="Attachments")
    syphilis_images         = forms.CharField(required=False, widget=img_widget, label="Attachments")
    hiv_test_images         = forms.CharField(required=False, widget=img_widget, label="Attachments")
    hepa_b_images           = forms.CharField(required=False, widget=img_widget, label="Attachments")
    blood_typing_images     = forms.CharField(required=False, widget=img_widget, label="Attachments")
    ogct_50g_images         = forms.CharField(required=False, widget=img_widget, label="Attachments")
    
    form_type = forms.CharField(widget=forms.HiddenInput(attrs={'id': 'laboratory_form'}), initial="laboratory_form")

    def __init__(self, mhr_repo: MaternalHealthRecordRepository, mhr_id: int, *args, **kwargs):
        # Accept an optional `raw_files` kwarg (e.g. request.FILES) so callers
        # that don't pass files as the standard Form `files` arg can still
        # provide uploaded files to the form for pairing.
        raw_files = kwargs.pop('raw_files', None)
        super().__init__(*args, **kwargs)
        # preserve raw_files separately; Django will also set `self.files` when
        # the caller passes files to the Form constructor normally.
        self._raw_files = raw_files
        add_bootstrap_classes(self)
        # repository and id are stored for possible future use
        self._mhr_repo = mhr_repo
        self._mhr_id = mhr_id
        # track which tests already have DB records
        self._existing_tests = set()
        # track which tests already have images stored in DB (to disable upload)
        self._existing_image_tests = set()
        # Fetch existing lab results (presentation logic belongs to the form)
        logger = logging.getLogger(__name__)
        try:
            rows = []
            try:
                rows = self._mhr_repo.fetch_lab_results_by_mhr_id(self._mhr_id) or []
            except Exception:
                logger.exception('Failed to fetch existing lab results for mhr %s', self._mhr_id)
                rows = []

            if rows:
                id_to_key = {
                    1: 'urinalysis', 2: 'cbc', 3: 'sgot_sgpt', 4: 'creatinine_serum',
                    5: 'bua_bun', 6: 'syphilis', 7: 'hiv_test', 8: 'hepa_b',
                    9: 'blood_typing', 10: 'ogct_50g', 11: 'ogtt_100g'
                }

                for r in rows:
                    lab_id = r.get('lab_test_id') or r.get('lab_test')
                    try:
                        lab_id = int(lab_id) if lab_id is not None else None
                    except Exception:
                        lab_id = None
                    if not lab_id:
                        continue

                    key = id_to_key.get(lab_id)
                    if not key:
                        logger.debug('Unmapped lab_test_id %s for mhr %s', lab_id, self._mhr_id)
                        continue

                    self._existing_tests.add(key)

                    # populate result
                    result = r.get('result')
                    if result is not None:
                        try:
                            if isinstance(self.fields.get(key), forms.DecimalField):
                                self.fields[key].initial = Decimal(str(result))
                            else:
                                self.fields[key].initial = result
                        except Exception:
                            self.fields[key].initial = result

                    # populate date
                    date_key = f"{key}_date"
                    date_val = r.get('date_test') or r.get('date_tested')
                    if date_val:
                        try:
                            self.fields[date_key].initial = date_val
                        except Exception:
                            self.fields[date_key].initial = str(date_val)

                    # populate images: set initials and attach data attr for previews
                    images_key = f"{key}_images"
                    raw_imgs = r.get('result_img_path')
                    imgs_list = []
                    if raw_imgs:
                        if isinstance(raw_imgs, str):
                            try:
                                imgs_list = json.loads(raw_imgs)
                            except Exception:
                                imgs_list = [raw_imgs]
                        elif isinstance(raw_imgs, (list, tuple)):
                            imgs_list = list(raw_imgs)

                    if imgs_list:
                        try:
                            self.fields[images_key].initial = imgs_list
                            # expose preview urls to the widget via data attribute
                            self.fields[images_key].widget.attrs['data-existing-images'] = json.dumps(imgs_list)
                            # mark this test as having existing images and disable further uploads
                            self._existing_image_tests.add(key)
                            # disable the image input so the user cannot click Upload
                            try:
                                self.fields[images_key].widget.attrs['disabled'] = True
                            except Exception:
                                pass
                        except Exception:
                            self.fields[images_key].initial = imgs_list

                    # make result/date readonly but keep image input enabled so
                    # user can add images; preview click behavior will be handled
                    # by front-end using the data-existing-images attribute.
                    try:
                        if 'readonly' not in self.fields[key].widget.attrs:
                            self.fields[key].widget.attrs['readonly'] = True
                        if 'readonly' not in self.fields[date_key].widget.attrs:
                            self.fields[date_key].widget.attrs['readonly'] = True
                    except Exception:
                        logger.exception('Failed to mark fields readonly for key %s', key)
                # Ensure tests without images but with a result and date are
                # also treated as existing and marked readonly. This covers
                # the case where a test row exists with text+date but no
                # images; the user should not be able to edit those fields.
                for key in self._test_keys():
                    date_key = f"{key}_date"
                    try:
                        has_result = False
                        has_date = False
                        if key in self.fields:
                            init_val = self.fields[key].initial
                            has_result = init_val is not None and init_val != ''
                        if date_key in self.fields:
                            date_init = self.fields[date_key].initial
                            has_date = date_init is not None and date_init != ''

                        if has_result and has_date:
                            # mark readonly for this specific test
                            if key in self.fields:
                                self.fields[key].widget.attrs['readonly'] = True
                            if date_key in self.fields:
                                self.fields[date_key].widget.attrs['readonly'] = True
                            # also disable the image upload control for this test
                            images_key = f"{key}_images"
                            if images_key in self.fields:
                                try:
                                    self.fields[images_key].widget.attrs['disabled'] = True
                                except Exception:
                                    pass
                            # record server-side to prevent crafted uploads
                            self._existing_image_tests.add(key)

                        # Ensure image input is disabled only for tests that had images
                        images_key = f"{key}_images"
                        if key in self._existing_image_tests and images_key in self.fields:
                            self.fields[images_key].widget.attrs['disabled'] = True
                    except Exception:
                        logger.exception('Failed to finalize readonly/disabled for key %s', key)
        except Exception:
            logger.exception('Unexpected error during LaboratoryForm init for mhr %s', self._mhr_id)

    # -- Small, focused helpers so the pairing behaviour can be plugged/removed --
    def _test_keys(self) -> List[str]:
        """Return the base keys for all laboratory tests handled by this form."""
        return [
            'urinalysis', 'cbc', 'sgot_sgpt', 'creatinine_serum', 'bua_bun',
            'syphilis', 'hiv_test', 'hepa_b', 'blood_typing', 'ogct_50g'
        ]

    def _images_for_key(self, cleaned_data: Dict[str, Any], key: str) -> List[Any]:
        """Return a list of image objects (or filenames) for a given test key.

        This supports multiple possible sources:
        - files in `self.files` (typical Django request.FILES, supports getlist)
        - values already present in cleaned_data (e.g., lists of filenames)
        """
        images_key = f"{key}_images"
        imgs: List[Any] = []

        # Prefer explicitly provided raw files (form._raw_files) then fall
        # back to the Form.files attribute populated by Django.
        files_container = getattr(self, '_raw_files', None) or getattr(self, 'files', None)
        if files_container:
            # MultiValueDict from request.FILES supports getlist
            getlist = getattr(files_container, 'getlist', None)
            if callable(getlist):
                imgs = [i for i in list(files_container.getlist(images_key)) if i]
                if imgs:
                    return imgs
            # fallback - single entry
            single = files_container.get(images_key)
            if single:
                return [single]

        # fallback to cleaned_data value (tests in some callers provide image lists there)
        v = cleaned_data.get(images_key)
        if not v:
            return []
        if isinstance(v, (list, tuple)):
            return [i for i in list(v) if i]
        return [v] if v else []

    def _pair_single_test(self, cleaned_data: Dict[str, Any], key: str) -> Dict[str, Any]:
        """Pair a single test's description, date and images into a dict.

        Rules implemented:
        - If the test has a value or has images present, a corresponding date is required.
        - If no description/value is present, fall back to 'N/A'.
        - If no images are present that's allowed (images list will be empty).
        - Raises ValidationError when a required date is missing.
        """
        desc = cleaned_data.get(key)
        date_key = f"{key}_date"
        date_val = cleaned_data.get(date_key)
        images = self._images_for_key(cleaned_data, key)

        # Prevent uploading images when images already exist for this test in DB.
        if getattr(self, '_existing_image_tests', None) and key in self._existing_image_tests and images:
            raise ValidationError({f"{key}_images": f"Images already exist for {key}. To change them, edit the existing record or contact your administrator."})

        # normalize description
        if desc in (None, ''):
            desc_val = 'N/A'
        else:
            desc_val = desc

        # If the test has a value (not N/A) or has attachments, date is required
        has_meaningful_value = desc not in (None, '') or bool(images) or bool(date_val)
        if has_meaningful_value and not date_val:
            raise ValidationError({date_key: f'Date is required for {key}.'})

        # If everything is empty (no desc/date/images) return None to skip
        if not has_meaningful_value:
            return None

        return {
            'test_type': key,
            'date': date_val,
            'description': desc_val,
            'images': images,
        }

    def _pair_all_tests(self, cleaned_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Iterate all known tests and return a list of paired records.

        The output is a list of dicts with keys: test_type, date, description, images.
        Tests that have no data at all are skipped.
        """
        pairs: List[Dict[str, Any]] = []
        for k in self._test_keys():
            paired = self._pair_single_test(cleaned_data, k)
            if paired:
                pairs.append(paired)
        return pairs
    def clean(self):
        """Validate and pair lab tests -> stores result on `self.paired_tests`.

        The pairing logic is implemented inline here to keep all validation
        and normalization in one place. Behavior is unchanged from the
        previous helper-based implementation:
        - For each known test: gather description, date and images.
        - If a test has a value (non-empty description) or attachments,
          a date is required.
        - If description is empty, it falls back to 'N/A'.
        - Images may be absent; images are read from an attached files
          container (prefer `self._raw_files`, fallback to `self.files`).
        - The resulting list of paired tests is stored on
          `cleaned_data['paired_tests']` and `self.paired_tests`.
        """
        cleaned_data = super().clean()

        # Delegate pairing/validation to helper methods.
        pairs = self._pair_all_tests(cleaned_data)

        cleaned_data['paired_tests'] = pairs
        self.paired_tests = pairs

        return cleaned_data
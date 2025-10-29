import json
from datetime import date, time

from django.http import JsonResponse, HttpRequest, HttpResponseRedirect
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect as csrf_required

from authentication.guards import session_login_required, role_required
from src.infra.database.connection_adapter import ConnectionAdapter
from maternal.repository import MaternalHealthRecordRepository
from maternal.exceptions.maternal_exceptions import MaternalHealthRecordException
from maternal.forms.postpartum_record_form import PostpartumRecordForm


ALLOWED_ROLES = ("MIDWIFE", "Midwife", "midwife", "Barangay Health Worker", "bhw", "Super Admin")


@method_decorator(session_login_required, name="dispatch")
@method_decorator(role_required(*ALLOWED_ROLES), name="dispatch")
@method_decorator(csrf_required, name="dispatch")
class PostpartumRecordAPI(View):
    """API to insert a postpartum record.

    Accepts form-encoded POST (from modal) or JSON body. If called via form POST,
    redirects back to the record_detail page on success. If called with JSON, returns JSON.
    """

    def post(self, request: HttpRequest, *args, **kwargs):
        # Accept both JSON and form-encoded
        payload = None
        if request.content_type and 'application/json' in request.content_type:
            try:
                payload = json.loads(request.body.decode('utf-8') or '{}')
            except Exception:
                return JsonResponse({'success': False, 'message': 'Invalid JSON payload.'}, status=400)
        else:
            # use POST dict
            payload = {k: v for k, v in request.POST.items()}

        form = PostpartumRecordForm(data=payload)
        if not form.is_valid():
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': 'Validation failed.', 'errors': form.errors}, status=400)
            # for form POST, render to same page by redirecting with message
            # store message in session and redirect back
            request.session['postpartum_form_errors'] = form.errors
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

        data = form.cleaned_data

        # parse date/time types
        try:
            if isinstance(data['date_of_delivery'], str):
                parsed_date = date.fromisoformat(data['date_of_delivery'])
            else:
                parsed_date = data['date_of_delivery']
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid date_of_delivery.'}, status=400)

        try:
            if isinstance(data['time_of_delivery'], str):
                parts = data['time_of_delivery'].split(':')
                hh = int(parts[0]); mm = int(parts[1]); ss = int(parts[2]) if len(parts) > 2 else 0
                parsed_time = time(hh, mm, ss)
            else:
                parsed_time = data['time_of_delivery']
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid time_of_delivery.'}, status=400)

        try:
            mhr_id = int(data['maternal_record_id'])
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid maternal record id.'}, status=400)

        staff_id = request.session.get('auth', {}).get('staff_id')
        try:
            staff_id = int(staff_id)
        except Exception:
            return JsonResponse({'success': False, 'message': 'Invalid staff id in session.'}, status=400)

        repo = MaternalHealthRecordRepository(ConnectionAdapter())

        try:
            res = repo.insert_postpartum_record_bhw(
                staff_id,
                mhr_id,
                parsed_date,
                parsed_time,
                data.get('attended_by_id'),
                data.get('attended_by_rolename'),
                data.get('place_of_delivery_id'),
                data.get('outcome'),
                bool(data.get('iron_supplementation')),
                bool(data.get('vit_a_supplementation')),
                bool(data.get('mebendazole_given')),
                data.get('lochial_discharges_baseline'),
                data.get('pads_per_day_baseline'),
            )
        except MaternalHealthRecordException as e:
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': e.message or str(e)}, status=400)
            request.session['postpartum_api_error'] = e.message or str(e)
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))
        except Exception as e:
            import logging
            logging.exception('Unexpected error inserting postpartum record')
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': 'Unexpected server error.'}, status=500)
            request.session['postpartum_api_error'] = 'Unexpected server error.'
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

        if not res:
            if request.content_type and 'application/json' in (request.content_type or ''):
                return JsonResponse({'success': False, 'message': 'Failed to save postpartum record.'}, status=500)
            request.session['postpartum_api_error'] = 'Failed to save postpartum record.'
            return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

        if request.content_type and 'application/json' in (request.content_type or ''):
            return JsonResponse({'success': True, 'message': 'Postpartum record saved.', 'result': res})

        # form POST -> redirect back to referring page
        return HttpResponseRedirect(request.META.get('HTTP_REFERER', '/'))

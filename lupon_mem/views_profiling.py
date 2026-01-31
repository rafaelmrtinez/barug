from django.shortcuts import render, redirect
from django.http import HttpRequest, HttpResponse
from authentication.guards import session_login_required, role_required
from authentication.utils import nocache
from django.views.decorators.csrf import csrf_protect
from django.contrib import messages
from datetime import datetime
from common.supabase_client import supabase
from bhw.forms import ResidentPersonalInfoForm, ResidentSocioeconomicForm

ROLE_LUPON_MEM = ("BARANGAY LUPON MEMBER", "Barangay Lupon Member", "lupon_mem", "Super Admin")

def _auth_role_name(request: HttpRequest) -> str:
    return (((request.session.get("auth") or {}).get("role_name")) or "Staff").title()

@session_login_required
@role_required(*ROLE_LUPON_MEM)
@csrf_protect
@nocache
def profile_personal_info(request: HttpRequest) -> HttpResponse:
    user_role = _auth_role_name(request)
    if request.method == 'POST':
        form = ResidentPersonalInfoForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data.copy()
            if 'dob' in data and data['dob']:
                data['dob'] = str(data['dob'])
            else:
                data['dob'] = None
            if data.get('mobile_num') and data['mobile_num'].strip() in ('', '+63'):
                data['mobile_num'] = None
            data['is_resident'] = request.POST.get('is_resident', '1') == '1'
            
            # Handle image upload
            if 'person_img' in request.FILES:
                import base64
                img_file = request.FILES['person_img']
                img_data = base64.b64encode(img_file.read()).decode('utf-8')
                data['person_img'] = f"data:{img_file.content_type};base64,{img_data}"
            
            request.session['profile_data'] = data
            return redirect('lupon_mem:profile_review')
    else:
        initial = request.session.get('profile_data', {})
        form = ResidentPersonalInfoForm(initial=initial)
    return render(request, 'lupon_mem/profiling/personal_info.html', {'form': form, 'page_path': f'{user_role} / Profile Resident / Personal Information', 'page_title': 'Profile Resident - Personal Information'})

@session_login_required
@role_required(*ROLE_LUPON_MEM)
@csrf_protect
@nocache
def profile_socioeconomic(request: HttpRequest) -> HttpResponse:
    return redirect('lupon_mem:profile_review')

@session_login_required
@role_required(*ROLE_LUPON_MEM)
@csrf_protect
@nocache
def profile_review(request: HttpRequest) -> HttpResponse:
    import logging
    logger = logging.getLogger(__name__)
    profile_data = request.session.get('profile_data', {})
    if not profile_data:
        return redirect('lupon_mem:profile_personal_info')
    
    if request.method == 'POST':
        try:
            auth = request.session.get('auth', {})
            performer_id = auth.get('staff_id', 1)
            def safe_int(val):
                if val and str(val).strip() and str(val).strip().lower() != 'none':
                    return int(val)
                return None
            
            payload = {
                'p_performer_id': performer_id,
                'p_first_name': profile_data.get('first_name'),
                'p_middle_name': profile_data.get('middle_name') or None,
                'p_last_name': profile_data.get('last_name'),
                'p_suffix': profile_data.get('suffix') or None,
                'p_birthdate': profile_data.get('dob') or '1900-01-01',
                'p_sex_id': int(profile_data.get('sex', 1)),
                'p_civil_status_id': int(profile_data.get('civil_status', 1)),
                'p_nationality_id': int(profile_data.get('nationality', 1)),
                'p_religion_id': int(profile_data.get('religion', 1)),
                'p_mobile_num': profile_data.get('mobile_num') if profile_data.get('mobile_num') and profile_data.get('mobile_num').strip() not in ('', '+63') else None,
                'p_email': profile_data.get('email') or None,
                'p_education_id': None,
                'p_employment_status_id': None,
                'p_residential_status_id': 2 if profile_data.get('is_resident', True) else 6,
                'p_person_img': profile_data.get('person_img') or None,
            }
            logger.info(f'[LUPON_MEM PROFILING] Submitting resident profile: {profile_data.get("first_name")} {profile_data.get("last_name")}')
            result = supabase.rpc('profile_resident_lupon', payload).execute()
            logger.info(f'[LUPON_MEM PROFILING] SUCCESS - Resident profile created: {profile_data.get("first_name")} {profile_data.get("last_name")}')
            del request.session['profile_data']
            request.session.modified = True
            
            profile_data['sex_display'] = 'Male' if profile_data.get('sex') == '1' else 'Female'
            profile_data['civil_status_display'] = {1: 'Single', 2: 'Married', 3: 'Widowed', 4: 'Separated', 5: 'Divorced'}.get(int(profile_data.get('civil_status', 1)))
            profile_data['nationality_display'] = {1: 'American', 2: 'Australian', 3: 'Brazilian', 4: 'British', 5: 'Canadian', 6: 'Chinese', 7: 'Filipino', 8: 'French', 9: 'German', 10: 'Indian', 11: 'Indonesian', 12: 'Italian', 13: 'Japanese', 14: 'Korean', 15: 'Malaysian', 16: 'Russian', 17: 'Saudi', 18: 'Spanish', 19: 'Thai', 20: 'Vietnamese'}.get(int(profile_data.get('nationality', 7)))
            profile_data['religion_display'] = {1: 'Agnostic', 2: 'Born Again', 3: 'Buddhist', 4: 'Christian', 5: 'Evangelical', 6: 'Hindu', 7: 'Iglesia Ni Cristo', 8: 'Islam', 9: "Jehovah's Witness", 10: 'Orthodox', 11: 'Protestant', 12: 'Roman Catholic', 13: 'Seventh-Day Adventist', 14: 'Others'}.get(int(profile_data.get('religion', 12)))
            
            user_role = _auth_role_name(request)
            return render(request, 'lupon_mem/profiling/review.html', {'data': profile_data, 'success': True, 'page_path': f'{user_role} / Profile Resident / Review', 'page_title': 'Profile Resident - Review'})
        except Exception as e:
            logger.error(f'[LUPON_MEM PROFILING] FAILED - Error creating resident profile: {str(e)}')
            messages.error(request, f'Error: {str(e)}')
    
    profile_data['sex_display'] = 'Male' if profile_data.get('sex') == '1' else 'Female'
    profile_data['civil_status_display'] = {1: 'Single', 2: 'Married', 3: 'Widowed', 4: 'Separated', 5: 'Divorced'}.get(int(profile_data.get('civil_status', 1)))
    profile_data['nationality_display'] = {1: 'American', 2: 'Australian', 3: 'Brazilian', 4: 'British', 5: 'Canadian', 6: 'Chinese', 7: 'Filipino', 8: 'French', 9: 'German', 10: 'Indian', 11: 'Indonesian', 12: 'Italian', 13: 'Japanese', 14: 'Korean', 15: 'Malaysian', 16: 'Russian', 17: 'Saudi', 18: 'Spanish', 19: 'Thai', 20: 'Vietnamese'}.get(int(profile_data.get('nationality', 7)))
    profile_data['religion_display'] = {1: 'Agnostic', 2: 'Born Again', 3: 'Buddhist', 4: 'Christian', 5: 'Evangelical', 6: 'Hindu', 7: 'Iglesia Ni Cristo', 8: 'Islam', 9: "Jehovah's Witness", 10: 'Orthodox', 11: 'Protestant', 12: 'Roman Catholic', 13: 'Seventh-Day Adventist', 14: 'Others'}.get(int(profile_data.get('religion', 12)))
    user_role = _auth_role_name(request)
    return render(request, 'lupon_mem/profiling/review.html', {'data': profile_data, 'success': False, 'page_path': f'{user_role} / Profile Resident / Review', 'page_title': 'Profile Resident - Review'})

from django.http import JsonResponse
from django.db import connection
from authentication.guards import session_login_required, role_required

LUPON_ROLES = {"BARANGAY LUPON MEMBER", "BARANGAY LUPON PRESIDENT"}

@session_login_required
@role_required(*LUPON_ROLES, "barangay treasurer")
def hearing_status_api(request, case_id: int):
    """Get hearing status and current step for a case using fn_case_mediation_hearings function."""
    with connection.cursor() as cur:
        cur.execute("SELECT * FROM fn_case_mediation_hearings(%s)", [case_id])
        hearings = cur.fetchall()
        
        # Analyze hearings to determine current step
        current_step = 'start'
        hearing_no = 1
        hearing_attempt = 1
        hearing_held = False
        
        if hearings:
            # Sort by hearing_no
            sorted_hearings = sorted(hearings, key=lambda x: x[0])  # hearing_no column
            latest_hearing = sorted_hearings[-1]
            
            hearing_no = latest_hearing[0]  # hearing_no
            source = latest_hearing[1]      # source (KP-8 or KP-12)
            hearing_held = latest_hearing[7] # hearing_held
            settlement_outcome = latest_hearing[10] # settlement_outcome
            
            # Determine current step based on hearing data
            if hearing_no == 1:  # PB Mediation
                if not hearing_held:
                    current_step = 'kp9_mediation'
                elif settlement_outcome == 'SETTLED':
                    current_step = 'kp16_mediation'
                elif settlement_outcome in ['NOT_SETTLED', 'BOTH_NO_SHOW']:
                    current_step = 'kp10'  # Move to Pangkat
                else:
                    current_step = 'kp9_mediation'
            elif hearing_no == 2:  # First Pangkat
                if not hearing_held:
                    current_step = 'kp9_pangkat1'
                elif settlement_outcome == 'SETTLED':
                    current_step = 'kp16_pangkat1'
                else:
                    current_step = 'kp12_second'  # Second Pangkat
            elif hearing_no == 3:  # Second Pangkat
                if not hearing_held:
                    current_step = 'kp9_pangkat2'
                elif settlement_outcome == 'SETTLED':
                    current_step = 'kp16_pangkat2'
                else:
                    current_step = 'arbitration_or_cert'
        
        return JsonResponse({
            'hearing_held': hearing_held,
            'hearings_count': len(hearings),
            'current_step': current_step,
            'hearing_no': hearing_no,
            'hearing_attempt': hearing_attempt
        })
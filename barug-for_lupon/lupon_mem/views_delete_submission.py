# lupon_mem/views_delete_submission.py
from django.shortcuts import redirect
from django.contrib import messages
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger(__name__)

@require_http_methods(["POST", "DELETE"])
def delete_submission(request, submission_id):
    """
    Delete a form submission and all its associated answers.
    Due to CASCADE constraints, deleting the submission will automatically delete all answers.
    """
    try:
        with connection.cursor() as cursor:
            # First, check if the submission exists and get case info
            cursor.execute("""
                SELECT blotter_case_id, form_id, status
                FROM blotter_kp_submission
                WHERE submission_id = %s
            """, [submission_id])
            
            result = cursor.fetchone()
            
            if not result:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Submission not found'}, status=404)
                messages.error(request, 'Form submission not found.')
                return redirect('lupon_mem:case_list')
            
            case_id, form_id, status = result
            
            # Delete the submission (answers will be deleted automatically due to CASCADE)
            cursor.execute("""
                DELETE FROM blotter_kp_submission
                WHERE submission_id = %s
            """, [submission_id])
            
            deleted_count = cursor.rowcount
            
            if deleted_count > 0:
                logger.info(f"Deleted submission {submission_id} for case {case_id}")
                
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': True,
                        'message': 'Form deleted successfully',
                        'case_id': case_id
                    })
                
                messages.success(request, 'Form submission deleted successfully.')
                return redirect('lupon_mem:case_detail', case_id=case_id)
            else:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'error': 'Failed to delete submission'}, status=500)
                messages.error(request, 'Failed to delete form submission.')
                return redirect('lupon_mem:case_detail', case_id=case_id)
                
    except Exception as e:
        logger.error(f"Error deleting submission {submission_id}: {str(e)}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, f'Error deleting form: {str(e)}')
        return redirect('lupon_mem:case_list')

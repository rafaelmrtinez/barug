# Helper function to format filter display
def format_report_scope(complaint_title_id, case_nature_id, date_from, date_to, report_type="cases"):
    """Format a professional report scope sentence"""
    from datetime import datetime as dt
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    
    filter_style = ParagraphStyle(
        'FilterStyle',
        parent=None,
        fontSize=11,
        spaceAfter=15,
        alignment=1,
        textColor=colors.HexColor('#333333')
    )
    
    scope_parts = []
    
    if complaint_title_id:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT complaint_title_name FROM complaint_title WHERE complaint_title_id = %s", [complaint_title_id])
            row = cur.fetchone()
            if row:
                scope_parts.append(f"<b>{row[0]}</b> cases")
    
    if case_nature_id:
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SELECT case_name FROM case_nature WHERE case_nature_id = %s", [case_nature_id])
            row = cur.fetchone()
            if row:
                scope_parts.append(f"cases of <b>{row[0]}</b> nature")
    
    if date_from and date_to:
        df = dt.strptime(date_from, '%Y-%m-%d')
        dt_obj = dt.strptime(date_to, '%Y-%m-%d')
        date_text = f"from <b>{df.strftime('%B %d, %Y')}</b> to <b>{dt_obj.strftime('%B %d, %Y')}</b>"
    elif date_from:
        df = dt.strptime(date_from, '%Y-%m-%d')
        date_text = f"from <b>{df.strftime('%B %d, %Y')}</b> onwards"
    elif date_to:
        dt_obj = dt.strptime(date_to, '%Y-%m-%d')
        date_text = f"up to <b>{dt_obj.strftime('%B %d, %Y')}</b>"
    else:
        date_text = None
    
    if scope_parts or date_text:
        scope_text = f"This report covers "
        if scope_parts:
            scope_text += " and ".join(scope_parts)
        else:
            scope_text += f"all {report_type}"
        if date_text:
            scope_text += f" {date_text}"
        scope_text += "."
    else:
        scope_text = f"This report covers all {report_type} in the system."
    
    return scope_text, filter_style

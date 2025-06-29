from django.shortcuts import render

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Clerk'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.
def activity_log(request):
    return render(request, "activity_log.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Activity Log',
        'page_title' : 'Activity Log',
        'user_role_template' : user_role_template,
    })

def authentication_log(request):
    return render(request, "authentication_log.html", {
        'user_fullname' : user_fullname,
        'user_role' : user_role,
        'page_path' : f'{user_role} / Authentication Log',
        'page_title' : 'Authentication Log',
        'user_role_template' : user_role_template,
    })

def user_registration_log(request):
    return render(request, 'user_registration_log.html', {
        'user_fullname': user_fullname,
        'user_role': user_role,
        'page_path': f'{user_role} / User Registration Log',
        'page_title': 'User Registration Log',
        'user_role_template': user_role_template,
    })
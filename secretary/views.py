from django.shortcuts import render
from django.core.paginator import Paginator

#need back-end for proper assignment
user_fullname = 'lname, fname mname suffix'
user_role = 'Barangay Secretary'

user_role_template = user_role.lower().replace(' ', '_')

# Create your views here.

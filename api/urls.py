# api/urls.py
from django.urls import path
from .views_mobile import residents_search

urlpatterns = [
    path("mobile/residents/search", residents_search),
]

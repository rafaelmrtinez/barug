"""
URL configuration for barug project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from authentication import views as auth_view

urlpatterns = [
    path("", auth_view.login, name="login"),
    path("admin/", include("staff_admin.urls", namespace="staff_admin")),
    path("authentication/", include("authentication.urls", namespace="authentication")),
    path("bhw/", include("bhw.urls", namespace="bhw")),
    path("captain/", include("captain.urls", namespace="captain")),
    path("clerk/", include("clerk.urls", namespace="clerk")),
    path("lupon_mem/", include("lupon_mem.urls", namespace="lupon_mem")),
    path("lupon_pres/", include("lupon_pres.urls", namespace="lupon_pres")),
    path("person/", include("resident.urls", namespace="resident")),
    path("secretary/", include("secretary.urls", namespace="secretary")),
    path("treasurer/", include("treasurer.urls", namespace="treasurer")),
]

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
    # Admin
    path('admin/', admin.site.urls),

    # Web URLs (HTML)
    path("", auth_view.login, name="login"),
    path("authentication/", include("authentication.urls", namespace="authentication")),
    path("event_logs/", include("event_logs.urls", namespace="event_logs")),
    path("resident/", include("resident.urls", namespace="resident")),

    # API v1
    path('api/v1/residents/', include('resident.api_urls')),

    path('api/auth/', include('authentication.api_urls')),
]

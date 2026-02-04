from django.http import HttpRequest, HttpResponse
from django.views import View


# Create your views here.
class HealthCheckView(View):
    
    def get(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200)
    
    def head(self, request:HttpRequest) -> HttpResponse:
        return HttpResponse(status=204) 
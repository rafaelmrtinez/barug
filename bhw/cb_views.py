

from django.views.generic import TemplateView


class HouseholdView(TemplateView):
    """Renders the household registration template for BHW."""
    template_name = 'bhw/household/register.html'
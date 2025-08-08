from rest_framework.request import Request


class CustomRateLimiter:

    @staticmethod
    def is_ratelimited(request: Request) -> bool:
        """
        Check if the request is rate-limited based on the defined rate.
        """
        if getattr(request, 'limited', False):
            return True
        return False
# lupon_mem/views_hearings.py
from __future__ import annotations
from django.contrib import messages
from django.shortcuts import redirect
from django.http import HttpRequest
from authentication.guards import session_login_required, role_required
from .views_shared import LUPON_ROLES, _hearing_gate

# (This module is a stub for future hearing-specific POST actions like “mark held”.
#  Your current hearing logic lives inside helper gates and KP-16 submit hook.)
#  Keeping it minimal now to avoid duplicating code.

"""
TEMPORARY diagnostic instrumentation for the production "2FA Invalid code"
incident (2026-09-14). Wraps three points in the login-verification path to
log what actually happens, without changing behavior at all -- every DB
write / throttle / replay side effect, and every real validation outcome,
still happens exactly as before via the original methods:

  1. TOTPDevice.verify_token() -- logs the raw received token next to an
     independently-computed expected code, computed in the SAME function
     call at the SAME instant, eliminating any cross-process/cross-
     container timing question.
  2. TokenForm.clean() -- logs BEFORE any validation runs, including the
     raw otp_token value straight from POST data. This is the one that
     matters if verify_token() is never even reached (e.g. an initial
     round of testing showed NO log from #1 at all on a failing attempt --
     which would mean form validation is failing before the token check,
     and wagtail_2fa's template shows the same generic "Invalid code" text
     for ANY form error, not just a wrong token).
  3. LoginView.form_invalid() -- logs the full error dict and raw POST
     keys/values whenever the form is rejected for any reason.

Every theory reachable through reasoning about django_otp/wagtail_2fa's own
code (replay protection, throttling, duplicate devices, session/auth state,
inter-instance clock skew, browser autofill) has been ruled out against this
incident already -- this is for direct observation of the real request.

Remove this file and its one line in wtrx/apps.py once root cause is found
-- this is not meant to ship long-term.
"""

import logging
import time

from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice
from wagtail_2fa import forms as wagtail_2fa_forms
from wagtail_2fa import views as wagtail_2fa_views

logger = logging.getLogger("wtrx.debug_2fa")

_original_verify_token = TOTPDevice.verify_token
_original_token_form_clean = wagtail_2fa_forms.TokenForm.clean
_original_form_invalid = wagtail_2fa_views.LoginView.form_invalid


def _instrumented_verify_token(self, token):
    now = time.time()
    pre_drift = self.drift
    pre_last_t = self.last_t

    totp = TOTP(self.bin_key, self.step, self.t0, self.digits, pre_drift)
    totp.time = now
    try:
        expected_now = str(totp.token()).zfill(self.digits)
    except Exception:
        expected_now = "<error computing>"

    result = _original_verify_token(self, token)

    logger.warning(
        "2FA_DEBUG device_id=%s user_id=%s confirmed=%s received_token=%r "
        "expected_token_now=%s step=%s digits=%s t0=%s tolerance=%s "
        "drift_before=%s last_t_before=%s now_unix=%.3f result=%s",
        self.pk,
        self.user_id,
        self.confirmed,
        token,
        expected_now,
        self.step,
        self.digits,
        self.t0,
        self.tolerance,
        pre_drift,
        pre_last_t,
        now,
        result,
    )
    return result


def _instrumented_token_form_clean(self):
    """
    Logs BEFORE any validation runs, so we see this even if verify_token()
    is never reached at all (e.g. the otp_token field itself is empty/
    missing, which would explain the generic "Invalid code" message wagtail_
    2fa's template shows for ANY form error, not just a wrong token).
    """
    logger.warning(
        "2FA_DEBUG_FORM_CLEAN user=%r user_id=%s otp_token_raw=%r "
        "cleaned_data_before=%r field_errors_so_far=%r",
        getattr(self.user, "username", None),
        getattr(self.user, "pk", None),
        self.data.get("otp_token"),
        dict(self.cleaned_data),
        dict(self.errors) if self.errors else None,
    )
    return _original_token_form_clean(self)


def _instrumented_form_invalid(self, form):
    logger.warning(
        "2FA_DEBUG_FORM_INVALID errors=%r post_otp_token=%r post_keys=%r "
        "user=%r session_key=%r",
        dict(form.errors),
        self.request.POST.get("otp_token"),
        list(self.request.POST.keys()),
        getattr(self.request.user, "username", None),
        self.request.session.session_key,
    )
    return _original_form_invalid(self, form)


def patch_totp_verify_token_logging():
    TOTPDevice.verify_token = _instrumented_verify_token
    wagtail_2fa_forms.TokenForm.clean = _instrumented_token_form_clean
    wagtail_2fa_views.LoginView.form_invalid = _instrumented_form_invalid

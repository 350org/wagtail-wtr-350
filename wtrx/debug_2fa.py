"""
TEMPORARY diagnostic instrumentation for the production "2FA Invalid code"
incident (2026-09-14). Wraps TOTPDevice.verify_token() to log its exact
inputs and the independently-computed expected code at the same instant,
without changing its behavior at all -- every DB write / throttle / replay
side effect still happens exactly as before via the original method.

Every theory reachable through reasoning about django_otp/wagtail_2fa's own
code (replay protection, throttling, duplicate devices, session/auth state,
inter-instance clock skew, browser autofill) has been ruled out against this
incident. This computes the expected code in the SAME function call, on the
SAME process, at the SAME instant as the real check -- eliminating every
cross-process/cross-container timing question -- so the log line directly
answers whether the submitted token matches what the server computes right
then, and if not, whether that's a clock/secret problem or something else
entirely (e.g. the raw token value itself being mangled somewhere upstream).

Remove this file and its one line in wtrx/apps.py once root cause is found
-- this is not meant to ship long-term.
"""

import logging
import time

from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

logger = logging.getLogger("wtrx.debug_2fa")

_original_verify_token = TOTPDevice.verify_token


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


def patch_totp_verify_token_logging():
    TOTPDevice.verify_token = _instrumented_verify_token

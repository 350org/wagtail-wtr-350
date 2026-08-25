/**
 * Defaults the Draftail rich-text toolbar to "pinned" (sticky, always
 * visible) for any admin user who hasn't already set a preference.
 *
 * Wagtail's Draftail editor remembers the floating/sticky toolbar choice
 * per-browser in localStorage under "wagtail:draftail-toolbar" (see
 * wagtailadmin/js/draftail.js) -- there's no server-side setting for it.
 * The key is only ever written once a user clicks the pin/unpin button, so
 * its absence here means "never touched it", not "explicitly chose
 * floating" -- setting it once, only when absent, gives everyone a pinned
 * toolbar by default without overriding anyone who already made a choice
 * either way.
 */
(function () {
    "use strict";

    try {
        if (!localStorage.getItem("wagtail:draftail-toolbar")) {
            localStorage.setItem("wagtail:draftail-toolbar", "sticky");
        }
    } catch (e) {
        // localStorage unavailable (private browsing, disabled, etc.) -- no-op.
    }
})();

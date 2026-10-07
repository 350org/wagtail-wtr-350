/**
 * "Around the World" region switcher modal.
 * Opens/closes the native <dialog> in regional_site_switcher.html:
 *   [data-regional-sites-trigger] — button that opens the dialog
 *   [data-regional-sites-dialog]  — the <dialog> itself
 *   [data-regional-sites-close]   — button inside the dialog that closes it
 *
 * showModal() gives Escape-to-close for free. A click on the dialog's own
 * ::backdrop still needs wiring by hand — <dialog> doesn't close on that by
 * default — detected by checking the click landed on the <dialog> element
 * itself rather than one of its children (the backdrop sits behind the
 * dialog's own box, so a click that reaches the dialog element and not a
 * descendant is necessarily outside that box).
 */
class RegionalSiteModal {
    static init() {
        const triggers = document.querySelectorAll('[data-regional-sites-trigger]');
        triggers.forEach((trigger) => {
            // Prevent duplicate event listeners if init() is called again
            if (trigger.hasAttribute('data-regional-sites-initialized')) { return; }
            trigger.setAttribute('data-regional-sites-initialized', '');

            const wrapper = trigger.closest('.wtr-regional-site-switcher');
            const dialog = wrapper ? wrapper.querySelector('[data-regional-sites-dialog]') : null;
            if (!dialog) { return; }

            trigger.addEventListener('click', () => {
                dialog.showModal();
            });

            const closeButton = dialog.querySelector('[data-regional-sites-close]');
            if (closeButton) {
                closeButton.addEventListener('click', () => dialog.close());
            }

            dialog.addEventListener('click', (event) => {
                if (event.target === dialog) {
                    dialog.close();
                }
            });
        });
    }
}

export default RegionalSiteModal;

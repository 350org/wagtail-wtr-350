/**
 * Person card "Read more" bio modal.
 * Opens/closes the native <dialog> in person_card.html:
 *   [data-bio-content]        — the clamped (line-clamp-3) bio <p>
 *   [data-person-bio-trigger] — button that opens the dialog, hidden by
 *                                default in the markup, a sibling of the
 *                                clamped content
 *   [data-person-bio-dialog]  — the <dialog> itself, holding the full
 *                                (unclamped) bio
 *   [data-person-bio-close]   — button inside the dialog that closes it
 *
 * Whether a given bio is long enough to need the trigger at all can only
 * be known after layout (scrollHeight vs clientHeight), so the trigger
 * starts hidden and this only reveals it where the clamp actually bites —
 * a short bio that already fits in 3 lines gets no trigger.
 *
 * Same showModal()/backdrop-click-to-close conventions as
 * RegionalSiteModal (regional-site-modal.js) — see that file's own
 * comment for why the backdrop click needs wiring by hand. Trigger and
 * dialog are looked up via .closest('.wtr-person-card') rather than a
 * page-wide id, the same per-instance scoping regional_site_switcher.html
 * uses, since a PersonCardGridBlock puts many of these on one page and
 * each needs its own independent dialog.
 */
class PersonBioModal {
    static init() {
        const contents = document.querySelectorAll('[data-bio-content]');
        contents.forEach((content) => {
            // Prevent duplicate event listeners if init() is called again
            if (content.hasAttribute('data-bio-initialized')) { return; }
            content.setAttribute('data-bio-initialized', '');

            const card = content.closest('.wtr-person-card');
            if (!card) { return; }

            const trigger = card.querySelector('[data-person-bio-trigger]');
            const dialog = card.querySelector('[data-person-bio-dialog]');
            if (!trigger || !dialog) { return; }

            // A bio that already fits within the clamp needs no trigger.
            if (content.scrollHeight <= content.clientHeight + 1) { return; }

            trigger.classList.remove('hidden');
            trigger.addEventListener('click', () => {
                dialog.showModal();
            });

            const closeButton = dialog.querySelector('[data-person-bio-close]');
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

export default PersonBioModal;

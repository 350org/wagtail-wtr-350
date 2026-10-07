/**
 * CardBlock's "modal content" CTA (components/card.html):
 *   [data-card-modal-trigger] — the card's button, opens the dialog
 *   [data-card-modal-dialog]  — the native <dialog> holding the content
 *   [data-card-modal-close]   — close button inside the dialog
 *
 * Same showModal()/backdrop-click-to-close conventions as
 * ActionKitPetitionModal. Trigger and dialog are paired via
 * .closest('.wtr-card'), not a page-wide id — a card grid carries one
 * dialog per card.
 */
class CardModal {
    static init() {
        const triggers = document.querySelectorAll('[data-card-modal-trigger]');
        triggers.forEach((trigger) => {
            if (trigger.hasAttribute('data-card-modal-initialized')) { return; }
            trigger.setAttribute('data-card-modal-initialized', '');

            const card = trigger.closest('.wtr-card');
            const dialog = card && card.querySelector('[data-card-modal-dialog]');
            if (!dialog) { return; }

            trigger.addEventListener('click', () => {
                dialog.showModal();
            });

            const closeButton = dialog.querySelector('[data-card-modal-close]');
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

export default CardModal;

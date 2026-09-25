/**
 * "View the full petition text" modal on SignupActionKitBlock
 * (_actionkit_intro.html):
 *   [data-ak-petition-trigger] — button in the copy column that opens it
 *   [data-ak-petition-dialog]  — the native <dialog> holding ActionKit's
 *                                own petition text
 *   [data-ak-petition-close]   — close button inside the dialog
 *
 * Same showModal()/backdrop-click-to-close conventions as PersonBioModal.
 * Trigger and dialog are paired via .closest('.wtr-signup-actionkit'), not
 * a page-wide id — a page can carry more than one signup panel, each
 * rendering its own copy of the same ActionKit page's text.
 */
class ActionKitPetitionModal {
    static init() {
        const triggers = document.querySelectorAll('[data-ak-petition-trigger]');
        triggers.forEach((trigger) => {
            if (trigger.hasAttribute('data-ak-petition-initialized')) { return; }
            trigger.setAttribute('data-ak-petition-initialized', '');

            const panel = trigger.closest('.wtr-signup-actionkit');
            const dialog = panel && panel.querySelector('[data-ak-petition-dialog]');
            if (!dialog) { return; }

            trigger.addEventListener('click', () => {
                dialog.showModal();
            });

            const closeButton = dialog.querySelector('[data-ak-petition-close]');
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

export default ActionKitPetitionModal;

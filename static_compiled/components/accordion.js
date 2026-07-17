/**
 * Accordion toggle component.
 * Expands/collapses accordion items using data attributes:
 *   [data-accordion]         — container element
 *   [data-accordion-toggle]  — button that toggles an item
 *   [data-accordion-content] — content panel to show/hide
 *
 * Each toggle button and its sibling content panel are found within the
 * same parent element (the accordion item).
 *
 * On init, each content panel receives a unique ID and its toggle button
 * gets an aria-controls attribute pointing to that ID. Content panels get
 * role="region" and aria-labelledby pointing back to the toggle button.
 */
class Accordion {
    static _counter = 0;

    static init() {
        const accordions = document.querySelectorAll('[data-accordion]');
        accordions.forEach((accordion) => {
            const toggles = accordion.querySelectorAll('[data-accordion-toggle]');
            toggles.forEach((toggle) => {
                // Prevent duplicate event listeners if init() is called again
                if (toggle.hasAttribute('data-accordion-initialized')) { return; }
                toggle.setAttribute('data-accordion-initialized', '');

                const item = toggle.parentElement;
                const content = item.querySelector('[data-accordion-content]');
                if (!content) { return; }

                // Assign unique IDs and wire up aria relationships
                Accordion._counter += 1;
                if (!content.id) {
                    content.id = 'accordion-panel-' + Accordion._counter;
                }
                if (!toggle.id) {
                    toggle.id = 'accordion-toggle-' + Accordion._counter;
                }
                toggle.setAttribute('aria-controls', content.id);
                content.setAttribute('role', 'region');
                content.setAttribute('aria-labelledby', toggle.id);

                const chevron = toggle.querySelector('svg');

                // Sync chevron rotation with initial expanded state
                if (chevron && toggle.getAttribute('aria-expanded') === 'true') {
                    chevron.classList.add('rotate-180');
                }

                toggle.addEventListener('click', () => {
                    const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
                    toggle.setAttribute('aria-expanded', String(!isExpanded));
                    content.classList.toggle('hidden');
                    if (chevron) {
                        chevron.classList.toggle('rotate-180');
                    }
                });
            });
        });
    }
}

export default Accordion;

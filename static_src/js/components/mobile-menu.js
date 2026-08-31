/**
 * Mobile menu toggle component.
 * Toggles the mobile navigation menu (or, when
 * NavigationSettings.collapse_desktop_menu is on, the collapsed-desktop
 * dropdown that reuses the same markup — see AGENTS.md pitfall #18) open
 * and closed. This component is breakpoint-agnostic on purpose: it only
 * ever looks at the button/panel pair, never at viewport width, so it
 * behaves identically for either variant.
 *
 * Behaviour:
 * - Toggles aria-expanded and the panel's `hidden` class.
 * - Swaps the hamburger icon for a close (X) icon while open, via
 *   [data-mobile-menu-icon-open] / [data-mobile-menu-icon-close] — the
 *   same instant class-toggle idiom accordion.js already uses.
 * - Locks page scroll (via a `wtr-scroll-locked` class on <body>, see
 *   main.css) while the panel is open, so the page can't be scrolled out
 *   from under an open menu.
 * - Closes on Escape (returning focus to the toggle button), and on a
 *   click/tap outside both the panel and the toggle button.
 * - Closes when an anchor link inside the panel is clicked, so the user
 *   can see the target section after the smooth scroll.
 */
class MobileMenu {
    static init() {
        const toggleButtons = document.querySelectorAll('[data-mobile-menu-toggle]');
        toggleButtons.forEach((button) => {
            // Prevent duplicate event listeners if init() is called again
            if (button.hasAttribute('data-mobile-menu-initialized')) { return; }
            button.setAttribute('data-mobile-menu-initialized', '');

            const menuId = button.getAttribute('aria-controls');
            const menu = document.getElementById(menuId);
            if (!menu) { return; }

            const openIcon = button.querySelector('[data-mobile-menu-icon-open]');
            const closeIcon = button.querySelector('[data-mobile-menu-icon-close]');

            const open = () => {
                button.setAttribute('aria-expanded', 'true');
                menu.classList.remove('hidden');
                if (openIcon) { openIcon.classList.add('hidden'); }
                if (closeIcon) { closeIcon.classList.remove('hidden'); }
                document.body.classList.add('wtr-scroll-locked');
            };

            const close = () => {
                button.setAttribute('aria-expanded', 'false');
                menu.classList.add('hidden');
                if (openIcon) { openIcon.classList.remove('hidden'); }
                if (closeIcon) { closeIcon.classList.add('hidden'); }
                document.body.classList.remove('wtr-scroll-locked');
            };

            button.addEventListener('click', () => {
                const isExpanded = button.getAttribute('aria-expanded') === 'true';
                if (isExpanded) { close(); } else { open(); }
            });

            menu.querySelectorAll('a[href^="#"]').forEach((link) => {
                link.addEventListener('click', close);
            });

            // Outside click/tap closes the panel. Guarded so the button's
            // own click handler above (which already opened/closed the
            // panel) doesn't get double-processed here.
            document.addEventListener('click', (event) => {
                if (button.getAttribute('aria-expanded') !== 'true') { return; }
                if (menu.contains(event.target) || button.contains(event.target)) { return; }
                close();
            });

            // Escape closes the panel and returns focus to the toggle.
            document.addEventListener('keydown', (event) => {
                if (event.key !== 'Escape') { return; }
                if (button.getAttribute('aria-expanded') === 'true') {
                    close();
                    button.focus();
                }
            });
        });
    }
}

export default MobileMenu;

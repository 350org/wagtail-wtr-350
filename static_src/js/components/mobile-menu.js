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
 * - Fades and slides the panel in/out (opacity-0/-translate-y-2 base
 *   classes on the panel, removed on open) rather than an instant
 *   show/hide. `hidden` can't itself be transitioned (display:none has
 *   no intermediate state), so open() removes `hidden` first, forces a
 *   reflow, then removes the opacity/translate classes so the browser
 *   has a real "before" state to animate from; close() reverses that and
 *   only re-adds `hidden` after the transition's duration, guarded so a
 *   reopen during that window doesn't get hidden out from under it.
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
 * - For the fixed full-screen mobile overlay (not the compact, absolutely
 *   positioned collapsed-desktop dropdown, which already tracks the
 *   header via top-full in CSS) — pins the panel's `top` to the actual
 *   rendered bottom edge of [data-mobile-menu-header-row] every time it
 *   opens, rather than trusting the top-[65px] Tailwind class alone. That
 *   class is a reasonable no-JS fallback, but the header's real height
 *   drifts with content (a long regional label, font load timing, text
 *   wrapping at odd widths) — measuring it at open time is what actually
 *   keeps the overlay from drifting under/over the header row.
 */
const TRANSITION_MS = 200;
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
                // Only the fixed full-screen overlay needs this — the
                // absolute collapsed-desktop dropdown already tracks the
                // header's true height via top-full in CSS with no JS
                // measurement needed.
                if (getComputedStyle(menu).position === 'fixed') {
                    const headerRow = document.querySelector('[data-mobile-menu-header-row]');
                    if (headerRow) {
                        menu.style.top = headerRow.getBoundingClientRect().bottom + 'px';
                    }
                }
                menu.classList.remove('hidden');
                // Force a reflow so the browser registers the opacity-0/
                // -translate-y-2 starting state before it's removed below —
                // without this the two class changes coalesce into one
                // frame and there's nothing to transition from.
                void menu.offsetHeight;
                menu.classList.remove('opacity-0', '-translate-y-2');
                if (openIcon) { openIcon.classList.add('hidden'); }
                if (closeIcon) { closeIcon.classList.remove('hidden'); }
                document.body.classList.add('wtr-scroll-locked');
            };

            const close = () => {
                button.setAttribute('aria-expanded', 'false');
                menu.classList.add('opacity-0', '-translate-y-2');
                if (openIcon) { openIcon.classList.remove('hidden'); }
                if (closeIcon) { closeIcon.classList.add('hidden'); }
                document.body.classList.remove('wtr-scroll-locked');
                window.setTimeout(() => {
                    // Don't hide it out from under a reopen that happened
                    // during the closing transition.
                    if (button.getAttribute('aria-expanded') !== 'true') {
                        menu.classList.add('hidden');
                    }
                }, TRANSITION_MS);
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

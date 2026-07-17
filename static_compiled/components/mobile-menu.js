/**
 * Mobile menu toggle component.
 * Toggles the mobile navigation menu open/closed.
 * Also closes the menu when an anchor link inside it is clicked,
 * so the user can see the target section after smooth scroll.
 */
class MobileMenu {
    static init() {
        const toggleButtons = document.querySelectorAll('[data-mobile-menu-toggle]');
        toggleButtons.forEach((button) => {
            const menuId = button.getAttribute('aria-controls');
            const menu = document.getElementById(menuId);
            if (!menu) { return; }

            button.addEventListener('click', () => {
                const isExpanded = button.getAttribute('aria-expanded') === 'true';
                button.setAttribute('aria-expanded', String(!isExpanded));
                menu.classList.toggle('hidden');
            });

            menu.querySelectorAll('a[href^="#"]').forEach((link) => {
                link.addEventListener('click', () => {
                    button.setAttribute('aria-expanded', 'false');
                    menu.classList.add('hidden');
                });
            });
        });
    }
}

export default MobileMenu;

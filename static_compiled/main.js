// Main JavaScript entry point
import MobileMenu from './components/mobile-menu.js';
import Accordion from './components/accordion.js';
import FormAjax from './components/form-ajax.js';

document.addEventListener('DOMContentLoaded', () => {
    MobileMenu.init();
    Accordion.init();
    FormAjax.init();
});

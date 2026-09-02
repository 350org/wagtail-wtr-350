// Main JavaScript entry point
import MobileMenu from './components/mobile-menu.js';
import Accordion from './components/accordion.js';
import FormAjax from './components/form-ajax.js';
import RegionalSiteModal from './components/regional-site-modal.js';
import ActionKitCountryPrefill from './components/actionkit-country-prefill.js';
import PersonBioModal from './components/person-bio-modal.js';

document.addEventListener('DOMContentLoaded', () => {
    MobileMenu.init();
    Accordion.init();
    FormAjax.init();
    RegionalSiteModal.init();
    ActionKitCountryPrefill.init();
    PersonBioModal.init();
});

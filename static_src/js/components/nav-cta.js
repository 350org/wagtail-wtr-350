import ExternalLinks from './external-links.js';

/**
 * The header's CTA button (Settings > Navigation > CTA button, or a
 * navigation override's).
 *
 * With "CTA country links", the button renders without an href and
 * navigation/_nav_cta_country.html, an inline script right after it, puts
 * the visitor's link in place once Cloudflare's /cdn-cgi/trace answers
 * (pitfall #96). That has to happen before the parser moves on, not here:
 * a module only runs once the page has finished parsing, too late to beat
 * Fundraise Up's scan of the page's links.
 *
 * All this does is re-run the new-tab check on that link. ExternalLinks.init()
 * only sees links that have an href when it runs, so a link put in place
 * after it, once the lookup answers, would otherwise never be checked.
 *
 * A Fundraise Up link (?form=FUNXXXXXXX, #?form=FUNXXXXXXX) is left to
 * Fundraise Up, which binds it and opens the checkout in place.
 */
class NavCta {
    static init() {
        document.addEventListener('wtrx:nav-cta-ready', (event) => {
            ExternalLinks.refresh(event.detail);
        });
    }
}

export default NavCta;

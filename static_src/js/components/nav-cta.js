import ExternalLinks from './external-links.js';

/**
 * The header's CTA button (Settings > Navigation > CTA button, or a
 * navigation override's). Two jobs:
 *
 * 1. Geolocation. Points the button at the URL set for the visitor's
 *    country in its "CTA country links", e.g. a country-specific donation
 *    form. The country comes from Cloudflare's /cdn-cgi/trace edge endpoint,
 *    as in _fundraiseup_embed.html: it never reaches Django, so the
 *    edge-cached page stays the same for every visitor (pitfall #90). The
 *    server-rendered href is the fallback, kept for every other country,
 *    when the lookup fails (no Cloudflare in front, as on staging and in
 *    local development), and for a click that lands before the lookup
 *    answers. Reads the {country_code: url} map from the link's
 *    data-country-links (header.html, built by the nav_cta_country_links
 *    tag).
 *
 *    `?fundraiseup_country=<ISO code>` on the page URL skips the lookup, the
 *    same QA override the donate block reads, so one parameter checks every
 *    donate destination on a page without a VPN.
 *
 * 2. Fundraise Up checkout in place. Fundraise Up opens a campaign's
 *    checkout when a page *loads* with `?form=FUNXXXXXXX`, so a plain link
 *    to `?form=...` would reload the page first. A click on a CTA whose
 *    (possibly swapped) href is this same page with a `form` parameter calls
 *    FundraiseUp.openCheckout() instead. When Fundraise Up's installation
 *    snippet isn't on the page (integration disabled, live preview) the
 *    click is left alone and the reload opens the checkout as before.
 */
class NavCta {
    static init() {
        const links = document.querySelectorAll('.wtr-nav-cta');
        if (!links.length) { return; }

        links.forEach((link) => {
            link.addEventListener('click', NavCta.openFundraiseUpCheckout);
        });

        const geolocated = document.querySelectorAll('.wtr-nav-cta[data-country-links]');
        if (!geolocated.length) { return; }

        const override = new URLSearchParams(window.location.search).get('fundraiseup_country');
        if (override) {
            NavCta.applyCountry(geolocated, override.trim().toUpperCase());
            return;
        }

        fetch('/cdn-cgi/trace')
            .then((response) => (response.ok ? response.text() : ''))
            .then((text) => {
                const match = text.match(/^loc=([A-Z]{2})$/m);
                if (match) { NavCta.applyCountry(geolocated, match[1]); }
            })
            .catch(() => {});
    }

    static applyCountry(links, countryCode) {
        links.forEach((link) => {
            let urls;
            try {
                urls = JSON.parse(link.dataset.countryLinks);
            } catch (e) {
                return;
            }
            const url = urls[countryCode];
            if (!url) { return; }
            link.setAttribute('href', url);
            // ExternalLinks.init() decided new-tab against the fallback href.
            ExternalLinks.refresh(link);
        });
    }

    static openFundraiseUpCheckout(event) {
        // A modified or middle click means "open elsewhere"; let it through.
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) { return; }
        const link = event.currentTarget;
        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin || url.pathname !== window.location.pathname) { return; }
        const campaign = url.searchParams.get('form');
        if (!campaign || !window.FundraiseUp || typeof window.FundraiseUp.openCheckout !== 'function') { return; }
        event.preventDefault();
        window.FundraiseUp.openCheckout(campaign);
    }
}

export default NavCta;

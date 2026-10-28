import ExternalLinks from './external-links.js';

/**
 * Points the header's CTA button (Settings > Navigation > CTA button, or a
 * navigation override's) at the URL set for the visitor's country in its
 * "CTA country links", e.g. a country-specific donation form.
 *
 * The country comes from Cloudflare's /cdn-cgi/trace edge endpoint, as in
 * _fundraiseup_embed.html: it never reaches Django, so the edge-cached page
 * stays the same for every visitor (pitfall #90). The server-rendered href
 * is the fallback, kept for every other country, when the lookup fails (no
 * Cloudflare in front, as on staging and in local development), and for a
 * click that lands before the lookup answers.
 *
 * `?fundraiseup_country=<ISO code>` on the page URL skips the lookup, the
 * same QA override the donate block reads, so one parameter checks every
 * donate destination on a page without a VPN.
 *
 * Reads the {country_code: url} map from the link's data-country-links
 * (header.html, built by the nav_cta_country_links tag).
 */
class NavCtaGeolocation {
    static init() {
        const links = document.querySelectorAll('.wtr-nav-cta[data-country-links]');
        if (!links.length) { return; }

        const override = new URLSearchParams(window.location.search).get('fundraiseup_country');
        if (override) {
            NavCtaGeolocation.apply(links, override.trim().toUpperCase());
            return;
        }

        fetch('/cdn-cgi/trace')
            .then((response) => (response.ok ? response.text() : ''))
            .then((text) => {
                const match = text.match(/^loc=([A-Z]{2})$/m);
                if (match) { NavCtaGeolocation.apply(links, match[1]); }
            })
            .catch(() => {});
    }

    static apply(links, countryCode) {
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
}

export default NavCtaGeolocation;

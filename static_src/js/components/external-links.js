/**
 * Opens links to other sites in a new tab.
 *
 * Runs in the browser rather than at render time so it covers every link
 * on the page alike: template links, editor rich text, raw HTML blocks and
 * fetched third-party fragments (ActionKit). It also keeps the decision
 * out of the server-rendered page, which is edge-cached (pitfall #90).
 *
 * Reads two attributes from <body> (base.html):
 *   data-internal-hosts — comma-separated hosts that count as this site
 *                         (WTRX_INTERNAL_LINK_HOSTS), besides the current one
 *   data-new-tab-hint   — translated "(opens in a new tab)" text for screen
 *                         readers
 *
 * A link is external when it is http(s) and its host is neither the
 * current host nor one of the internal hosts. Relative links, #anchors,
 * mailto:/tel:, download links and links that already set a target are
 * left alone.
 *
 * A component that changes a link's href after load (nav-cta-geolocation.js)
 * calls refresh() on it afterwards, which undoes this script's own marking
 * and decides again for the new href.
 */
class ExternalLinks {
    static init() {
        const internalHosts = ExternalLinks.internalHosts();
        const hint = document.body.dataset.newTabHint || '';

        document.querySelectorAll('a[href]').forEach((link) => {
            if (ExternalLinks.isExternal(link, internalHosts)) {
                ExternalLinks.markExternal(link, hint);
            }
        });
    }

    static refresh(link) {
        if ('externalLabel' in link.dataset) {
            link.setAttribute('aria-label', link.dataset.externalLabel);
        }
        if ('externalMarked' in link.dataset) {
            link.removeAttribute('target');
            link.querySelectorAll('.wtr-new-tab-hint').forEach((span) => span.remove());
            delete link.dataset.externalMarked;
            delete link.dataset.externalLabel;
        }
        if (ExternalLinks.isExternal(link, ExternalLinks.internalHosts())) {
            ExternalLinks.markExternal(link, document.body.dataset.newTabHint || '');
        }
    }

    static internalHosts() {
        const internalHosts = new Set(
            (document.body.dataset.internalHosts || '')
                .split(',')
                .map((host) => host.trim().toLowerCase())
                .filter(Boolean)
        );
        internalHosts.add(window.location.hostname.toLowerCase());
        return internalHosts;
    }

    static isExternal(link, internalHosts) {
        if (link.hasAttribute('target') || link.hasAttribute('download')) { return false; }
        if (link.protocol !== 'http:' && link.protocol !== 'https:') { return false; }
        return !internalHosts.has(link.hostname.toLowerCase());
    }

    static markExternal(link, hint) {
        link.dataset.externalMarked = '';
        link.setAttribute('target', '_blank');
        const rel = new Set((link.getAttribute('rel') || '').split(/\s+/).filter(Boolean));
        rel.add('noopener');
        rel.add('noreferrer');
        link.setAttribute('rel', [...rel].join(' '));

        if (!hint) { return; }
        // An aria-label replaces the link's content as its accessible name,
        // so a visually hidden span would never be read; extend the label.
        const label = link.getAttribute('aria-label');
        if (label) {
            link.dataset.externalLabel = label;
            link.setAttribute('aria-label', `${label} ${hint}`);
            return;
        }
        const span = document.createElement('span');
        span.className = 'wtr-new-tab-hint sr-only';
        span.textContent = ` ${hint}`;
        link.appendChild(span);
    }
}

export default ExternalLinks;

/**
 * Marks this browser as having visited the site, so the country redirect
 * only ever fires on a visitor's first page view.
 *
 * Cloudflare Redirect Rules send a request for the bare homepage ("/") from
 * Brazil, Canada, France or Indonesia to that country's site. Each rule
 * skips requests carrying this cookie
 * (`not http.cookie contains "350_visited=1"`), so once any page has loaded
 * here — including the country page the redirect landed on — the visitor can
 * reach the English homepage, from the address bar or the footer's
 * "International" link, without being sent back.
 *
 * Set in the browser rather than by the server: pages are edge-cached and
 * must be identical for every visitor (pitfall #90). The cookie holds no
 * data beyond "has visited", and Cloudflare's cache key ignores it.
 */
const COOKIE_NAME = '350_visited';
const MAX_AGE_SECONDS = 60 * 60 * 24 * 365;

class VisitedCookie {
    static init() {
        if (document.cookie.split('; ').includes(`${COOKIE_NAME}=1`)) { return; }

        const secure = window.location.protocol === 'https:' ? '; Secure' : '';
        document.cookie = `${COOKIE_NAME}=1; Max-Age=${MAX_AGE_SECONDS}; Path=/; SameSite=Lax${secure}`;
    }
}

export default VisitedCookie;

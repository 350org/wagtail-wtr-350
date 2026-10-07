/**
 * Workaround for a bug in wagtail-ai <= 3.1.1's bundled field_panel.js: it
 * calls Wagtail's PreviewController.extractContent() without awaiting it.
 * extractContent() is async in Wagtail 7.x's core preview controller (it
 * awaits an accessibility-checks step before returning), so the un-awaited
 * call yields a bare Promise instead of the extracted {innerHTML, innerText,
 * lang} content. wagtail-ai's PromptContext.clean() then silently
 * substitutes the literal string "{content_html}"/"{content_text}" into the
 * prompt sent to the LLM instead of the actual page content, so every
 * AITitleFieldPanel/AIDescriptionFieldPanel "generate" action responds with
 * a confused answer about a missing placeholder rather than real content.
 *
 * Re-registers corrected versions of just the two affected context handlers
 * via wagtail-ai's own public ContextProvider.register() API. Remove this
 * once wagtail-ai ships a release that awaits extractContent() (tracked
 * upstream at https://github.com/wagtail/wagtail-ai).
 */
(function () {
    "use strict";

    async function extractPreviewContent() {
        var controller = window.wagtail && window.wagtail.app.queryController("w-preview");
        if (!controller) {
            return null;
        }
        if (!controller.ready) {
            await controller.checkAndUpdatePreview();
            await new Promise(function (resolve) {
                document.addEventListener("w-preview:loaded", resolve, { once: true });
            });
        }
        return await controller.extractContent();
    }

    function patchContextProvider() {
        var provider = window.wagtailAI && window.wagtailAI.ContextProvider;
        if (!provider) {
            return false;
        }
        provider.register("content_html", async function () {
            var content = await extractPreviewContent();
            return content ? content.innerHTML.trim() : undefined;
        });
        provider.register("content_text", async function () {
            var content = await extractPreviewContent();
            return content ? content.innerText.trim() : undefined;
        });
        return true;
    }

    // wagtail-ai's own script (which defines window.wagtailAI.ContextProvider)
    // may load before or after this one, depending on Wagtail's Media
    // aggregation order for the current admin page — poll briefly rather
    // than assume either ordering.
    if (!patchContextProvider()) {
        var attempts = 0;
        var interval = setInterval(function () {
            attempts += 1;
            if (patchContextProvider() || attempts > 40) {
                clearInterval(interval);
            }
        }, 50);
    }
})();

/**
 * Client-side half of the fix for GatedStreamBlockAdapter
 * (wtrx/blocks/__init__.py) -- see that class's docstring for the full
 * story. Short version: Wagtail's own StreamBlockDefinition (registered as
 * "wagtail.blocks.StreamBlock") builds its childBlockDefsByName lookup --
 * what an *already-placed* block looks itself up in when the StreamField
 * widget hydrates a page's existing value -- from the exact same
 * groupedChildBlockDefs argument the "Add block" picker uses. Filtering
 * that argument down to only the currently-enabled block types (as
 * IntegrationGatedStreamBlockMixin.sorted_child_blocks() does, so a
 * disabled integration's block type doesn't show up as addable) therefore
 * also broke hydration of any *existing* instance of that block type --
 * the widget crashed loading it, silently discarding it and everything
 * after it in the stream on the next save.
 *
 * GatedStreamBlockAdapter.js_args() sends the FULL (ungated)
 * groupedChildBlockDefs here instead, plus a separate hiddenBlockNames
 * list. This subclass builds childBlockDefsByName from that full list via
 * the normal StreamBlockDefinition constructor (so hydration always finds
 * every real block type), then narrows groupedChildBlockDefs itself
 * afterwards -- the only property the "Add block" picker
 * (StreamBlock.getBlockGroups()) actually reads -- to exclude the hidden
 * names, dropping any group left empty.
 *
 * Registered as "wtrx.blocks.GatedStreamBlock" -- see
 * GatedStreamBlockAdapter.js_constructor.
 */
(function () {
    "use strict";

    function register() {
        if (
            !window.wagtailStreamField ||
            !window.wagtailStreamField.blocks ||
            !window.wagtailStreamField.blocks.StreamBlockDefinition ||
            !window.telepath
        ) {
            // blocks.js is a hard dependency, loaded first via this
            // adapter's own Django Media declaration
            // (GatedStreamBlockAdapter.media) -- this guard only protects
            // against that ordering ever regressing, silently, rather than
            // crashing every StreamField widget on the page.
            return;
        }

        var StreamBlockDefinition = window.wagtailStreamField.blocks.StreamBlockDefinition;

        class GatedStreamBlockDefinition extends StreamBlockDefinition {
            constructor(name, groupedChildBlockDefs, initialChildStates, meta, hiddenBlockNames) {
                super(name, groupedChildBlockDefs, initialChildStates, meta);

                var hidden = {};
                (hiddenBlockNames || []).forEach(function (blockName) {
                    hidden[blockName] = true;
                });

                this.groupedChildBlockDefs = this.groupedChildBlockDefs
                    .map(function (group) {
                        var groupName = group[0];
                        var blockDefs = group[1].filter(function (blockDef) {
                            return !hidden[blockDef.name];
                        });
                        return [groupName, blockDefs];
                    })
                    .filter(function (group) {
                        return group[1].length > 0;
                    });
            }
        }

        window.wagtailStreamField.blocks.GatedStreamBlockDefinition = GatedStreamBlockDefinition;
        window.telepath.register("wtrx.blocks.GatedStreamBlock", GatedStreamBlockDefinition);
    }

    register();
})();

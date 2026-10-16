"""Per-language date formats, overriding Django's own (FORMAT_MODULE_PATH).

Templates render a post's date with ``|date:"DATE_FORMAT"`` so each language
tree gets its own order. A module here only needs the settings it changes;
anything it omits falls through to Django's locale formats. Lookup tries the
full locale before its base language (``pt_BR`` then ``pt``), so ``pt`` covers
pt-br, ``fr`` covers fr-fr/fr-ca and ``en`` covers en-ca/en-br.
"""

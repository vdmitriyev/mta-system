"""Markdown of the admins' texts (notifications, descriptions) as safe HTML.

Raw HTML in the text is shown as text, links work only with http(s), mailto or an
address of the app, and bare web addresses become links. A single line break stays.
"""

import re
import threading
import xml.etree.ElementTree as etree  # nosec B405 - builds elements, parses nothing

import markdown
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor
from markdown.treeprocessors import Treeprocessor
from markupsafe import Markup

SAFE_LINK = re.compile(r"^(https?://|mailto:|/(?!/)|#)", re.IGNORECASE)
BARE_URL = r"(?<![<\"'=])\bhttps?://[^\s<>()\[\]]+[^\s<>()\[\].,;:!?\"']"


class _BareUrl(InlineProcessor):
    def handleMatch(self, m, data):
        link = etree.Element("a", href=m.group(0))
        link.text = m.group(0)
        return link, m.start(0), m.end(0)


class _SafeLinks(Treeprocessor):
    def run(self, root):
        for element in root.iter():
            for name in ("href", "src"):
                value = element.get(name)
                if value is not None and not SAFE_LINK.match(value.strip()):
                    del element.attrib[name]
            if element.tag == "a" and str(element.get("href", "")).startswith("http"):
                element.set("target", "_blank")
                element.set("rel", "noopener")


class _SafeMarkdown(Extension):
    def extendMarkdown(self, md):
        # raw HTML is escaped, not passed on
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.inlinePatterns.register(_BareUrl(BARE_URL, md), "bare_url", 15)
        md.treeprocessors.register(_SafeLinks(md), "safe_links", 0)


# one parser per thread: building it loads the extensions each time
_local = threading.local()


def _parser() -> markdown.Markdown:
    parser = getattr(_local, "parser", None)
    if parser is None:
        parser = _local.parser = markdown.Markdown(
            extensions=[_SafeMarkdown(), "nl2br", "sane_lists"], output_format="html"
        )
    return parser


def to_html(text: str | None) -> str:
    if not text:
        return ""
    parser = _parser()
    try:
        return parser.convert(text)
    finally:
        parser.reset()


def render(text: str | None) -> Markup:
    """Jinja filter "markdown": the text as HTML"""

    return Markup(to_html(text))  # nosec B704 - raw HTML is escaped above


def render_inline(text: str | None) -> Markup:
    """Jinja filter "markdown_inline": for one line (no paragraph around it)"""

    html = to_html(text)
    if html.startswith("<p>") and html.endswith("</p>") and html.count("<p>") == 1:
        html = html[3:-4]
    return Markup(html)  # nosec B704 - raw HTML is escaped above

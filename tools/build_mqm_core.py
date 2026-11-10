"""Build localizelarge/data/mqm_core.json from the MQM Council's typology page.

    curl -L -o typology.html https://themqm.org/the-mqm-typology/
    python tools/build_mqm_core.py typology.html

The page shows the MQM Core typology as a tree: seven dimensions, each with a definition
and its error subtypes, each with a definition. This script copies names and definitions
as they stand on the page. The page gives no identifiers, so an id is made from each name
(lower case, hyphens). MQM materials are licensed CC BY 4.0 by The MQM Council; see NOTICE.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

from lxml import html

OUT = Path(__file__).resolve().parent.parent / "localizelarge" / "data" / "mqm_core.json"


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def own_text(button) -> str:
    """The label of a tree button, without its icon and its "3 types" counter."""
    parts = [button.text or ""]
    for child in button:
        if "typ-count" not in (child.get("class") or ""):
            parts.append(child.tail or "")
        else:
            parts.append(child.tail or "")
    return " ".join(" ".join(parts).split())


def first_definition(panel) -> str:
    for p in panel.xpath("./p[contains(@class, 'typ-def')]"):
        text = " ".join(p.text_content().split())
        if text and not text.startswith("Examples"):
            return text
    return ""


def main(path: str) -> int:
    doc = html.fromstring(Path(path).read_bytes())
    dimensions = []
    for dim in doc.xpath("//div[contains(@class, 'typ-dim')]"):
        button = dim.xpath("./button")[0]
        panel = dim.xpath("./div[contains(@class, 'typ-panel')]")[0]
        name = own_text(button)
        subtypes = []
        for sub in panel.xpath("./div[contains(@class, 'typ-sub')]"):
            sub_name = own_text(sub.xpath("./button")[0])
            sub_panel = sub.xpath("./div[contains(@class, 'typ-panel')]")[0]
            subtypes.append({"id": slug(sub_name), "name": sub_name,
                             "definition": first_definition(sub_panel)})
        dimensions.append({"id": slug(name), "name": name, "definition": first_definition(panel),
                           "subtypes": subtypes})
    data = {
        "name": "MQM Core",
        "source": "https://themqm.org/the-mqm-typology/",
        "retrieved": date.today().isoformat(),
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "MQM Core typology © The MQM Council (themqm.org), licensed under CC BY 4.0. "
                       "Names and definitions are unchanged; the identifiers were added by Localize Large.",
        "dimensions": dimensions,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(dimensions)} dimensions, {sum(len(d['subtypes']) for d in dimensions)} subtypes -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

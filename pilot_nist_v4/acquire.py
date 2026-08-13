"""Acquire the fixed, bounded NIST DADS pilot corpus; not a crawler."""
import hashlib
import json
import re
import urllib.request
from datetime import date
from html.parser import HTMLParser
from pathlib import Path


ENTRIES = [
    ("binary-search", "binarySearch.html", "named search algorithm"),
    ("quicksort", "quicksort.html", "named sorting algorithm with variants and complexity"),
    ("binary-search-tree", "binarySearchTree.html", "data structure and search/update concept"),
    ("heap-sort", "heapSort.html", "sorting algorithm linked to a data structure"),
    ("data-structure", "dataStructure.html", "sparse definitional entry"),
    ("bit-vector", "bitVector.html", "representation-related data structure"),
    ("search", "search.html", "general mechanism with alternatives"),
    ("breadth-first-search", "breadthfirst.html", "graph search using a queue"),
    ("depth-first-search", "depthfirst.html", "graph search with ambiguity and references"),
    ("counting-sort", "countingsort.html", "restricted-universe sort with auxiliary storage"),
    ("sort", "sort.html", "contract, stability and workload-dependent choices"),
    ("histogram-sort", "histogramSort.html", "performance and memory trade-offs"),
]
BASE_URL = "https://xlinux.nist.gov/dads/HTML/"


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_html(raw: bytes) -> str:
    parser = VisibleText()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = "\n".join(part.strip() for part in parser.parts if part.strip())
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip() + "\n"


def main():
    root = Path(__file__).parent
    source_dir = root / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source_id, filename, rationale in ENTRIES:
        url = BASE_URL + filename
        request = urllib.request.Request(url, headers={"User-Agent": "Atlas bounded NIST pilot"})
        with urllib.request.urlopen(request, timeout=30) as response:
            text = clean_html(response.read())
        target = source_dir / f"{source_id}.txt"
        target.write_text(text, encoding="utf-8")
        manifest.append({
            "source_id": source_id,
            "title": source_id.replace("-", " "),
            "kind": "NIST DADS reference entry",
            "url": url,
            "retrieved_at": date.today().isoformat(),
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "local_path": str(target),
            "selection_rationale": rationale,
            "cleanup": "HTML tags, scripts/styles and repeated whitespace removed mechanically; no related entry followed.",
        })
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

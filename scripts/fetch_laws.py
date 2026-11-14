"""Download the laws of the RAG corpus from zakon.rada.gov.ua.

    uv run python scripts/fetch_laws.py

zakon.rada.gov.ua is the official database of Ukrainian legislation kept by the
Verkhovna Rada. The script saves the print version of each act listed in LAWS to
`data/raw/laws/<id>.html`, with `<id>.json` next to it (url, title, download time).
The print version holds the full text in its current edition, without the site menus,
but with the editorial notes in braces ("{Із змінами, внесеними згідно із Законом …}").

Two of the acts are no longer in force and are kept on purpose, as an outdated version
of the current rules: the 1992 law on the lease of state property, replaced by the 2019
law, and the Commercial Code, repealed by Law No. 4196-IX. Which part of each act goes
into the corpus (e.g. only chapter 58 of the Civil Code) is decided by the ingestion,
not here.

Official documents of state bodies are not objects of copyright in Ukraine (Article 8
of the Law "On Copyright and Related Rights"), so the texts can be used freely.

Already downloaded acts are skipped; pass --force to download them again.
"""

import argparse
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "laws"
BASE = "https://zakon.rada.gov.ua/laws/show"
# The site answers 403 to clients without a browser-like User-Agent.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
DELAY_S = 2


@dataclass
class Law:
    id: str
    slug: str  # the act's number on zakon.rada.gov.ua
    title: str


LAWS = [
    Law("civil_code", "435-15", "Цивільний кодекс України"),
    Law(
        "law_157_ix",
        "157-20",
        "Закон України «Про оренду державного та комунального майна»",
    ),
    Law(
        "cmu_483_2020",
        "483-2020-п",
        "Постанова КМУ № 483 «Деякі питання оренди державного та комунального майна»",
    ),
    Law(
        "cmu_630_2021",
        "630-2021-п",
        "Постанова КМУ № 630 «Деякі питання розрахунку орендної плати за державне майно»",
    ),
    Law(
        "law_543_96",
        "543/96-вр",
        "Закон України «Про відповідальність за несвоєчасне виконання грошових зобов'язань»",
    ),
    # No longer in force: outdated versions of the rules above.
    Law(
        "law_2269_xii",
        "2269-12",
        "Закон України «Про оренду державного та комунального майна» (1992)",
    ),
    Law("commercial_code", "436-15", "Господарський кодекс України"),
]


def fetch(client: httpx.Client, law: Law, force: bool) -> bool:
    html_path = OUT / f"{law.id}.html"
    if html_path.exists() and not force:
        return False
    url = f"{BASE}/{law.slug}/print"
    response = client.get(url)
    response.raise_for_status()
    html_path.write_text(response.text, encoding="utf-8")
    meta = asdict(law) | {
        "url": url,
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (OUT / f"{law.id}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--force", action="store_true", help="download again")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=60, follow_redirects=True) as client:
        for law in LAWS:
            if fetch(client, law, args.force):
                size = (OUT / f"{law.id}.html").stat().st_size
                print(f"{law.id:<16} {size / 1024:>6.0f} KB  {law.title}")
                time.sleep(DELAY_S)
            else:
                print(f"{law.id:<16} already downloaded")


if __name__ == "__main__":
    main()

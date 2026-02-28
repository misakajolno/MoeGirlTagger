"""Build playable character libraries for Genshin Impact and Zenless Zone Zero."""

from __future__ import annotations

import csv
import datetime as dt
import re
from pathlib import Path
from typing import Dict, Iterable

import requests
from bs4 import BeautifulSoup

GENSHIN_PAGE = "https://genshin-impact.fandom.com/wiki/Character/List"
ZZZ_PAGE = "https://zenless-zone-zero.fandom.com/wiki/Agent/List"
GENSHIN_API = "https://api.hakush.in/gi/data/character.json"
ZZZ_API = "https://api.hakush.in/zzz/data/character.json"

OUTPUT_DIR = Path("data/character_library")
GENSHIN_OUTPUT = OUTPUT_DIR / "genshin_impact_characters.csv"
ZZZ_OUTPUT = OUTPUT_DIR / "zenless_zone_zero_agents.csv"

ZZZ_NAME_ALIAS = {
    "Alexandrina Sebastiane": "Rina",
    "Anby Demara": "Anby",
    "Anton Ivanov": "Anton",
    "Asaba Harumasa": "Harumasa",
    "Ben Bigger": "Ben",
    "Billy Kid": "Billy",
    "Burnice White": "Burnice",
    "Caesar King": "Caesar",
    "Corin Wickes": "Corin",
    "Ellen Joe": "Ellen",
    "Evelyn Chevalier": "Evelyn",
    "Grace Howard": "Grace",
    "Hugo Vlad": "Hugo",
    "Jane Doe": "Jane",
    "Koleda Belobog": "Koleda",
    "Komano Manato": "Manato",
    "Lucia Elowen": "Lucia",
    "Luciana de Montefio": "Lucy",
    "Nekomiya Mana": "Nekomata",
    "Nicole Demara": "Nicole",
    "Orphie Magnusson & Magus": "Orphie & Magus",
    "Piper Wheel": "Piper",
    "Tsukishiro Yanagi": "Yanagi",
    "Ukinami Yuzuha": "Yuzuha",
    "Vivian Banshee": "Vivian",
    "Von Lycaon": "Lycaon",
}


def normalize_key(value: str) -> str:
    """Normalize a key for fuzzy dictionary matching.

    Args:
        value: Raw string.

    Returns:
        Lowercase alphanumeric-only key.
    """
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def slugify(value: str) -> str:
    """Build a filesystem-safe identifier from a display name.

    Args:
        value: Character name.

    Returns:
        Snake-like slug.
    """
    result = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return re.sub(r"_+", "_", result)


def parse_zzz_release_date(text: str) -> str:
    """Extract ISO date from Agent/List release text.

    Args:
        text: Release cell text from the fandom table.

    Returns:
        Date string in YYYY-MM-DD format or empty string.
    """
    match = re.search(r"([A-Za-z]+ \d{2}, \d{4})", text)
    if not match:
        return ""
    parsed = dt.datetime.strptime(match.group(1), "%B %d, %Y")
    return parsed.date().isoformat()


def build_aliases(values: Iterable[str]) -> str:
    """Join distinct aliases into one pipe-separated string.

    Args:
        values: Alias candidates.

    Returns:
        Pipe-separated aliases.
    """
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return "|".join(result)


def map_genshin_rarity(rank: str) -> str:
    """Convert Hakush quality enum to star rarity string.

    Args:
        rank: Raw Hakush rank.

    Returns:
        Star rarity text.
    """
    mapping = {
        "QUALITY_ORANGE": "5",
        "QUALITY_ORANGE_SP": "5",
        "QUALITY_PURPLE": "4",
    }
    return mapping.get(rank, "")


def map_zzz_rarity(rank: int | str) -> str:
    """Convert ZZZ rank number to grade string.

    Args:
        rank: Raw rank from Hakush.

    Returns:
        Grade text.
    """
    mapping = {4: "S", 3: "A", 2: "B"}
    if isinstance(rank, int):
        return mapping.get(rank, str(rank))
    return str(rank)


def fetch_fandom_table(page: str) -> list[list[str]]:
    """Fetch first table from a fandom page via MediaWiki parse API.

    Args:
        page: Fandom wiki page URL.

    Returns:
        Table rows as plain text cells.
    """
    wiki_root = page.split("/wiki/")[0]
    page_title = page.split("/wiki/")[1]
    response = requests.get(
        f"{wiki_root}/api.php",
        params={"action": "parse", "page": page_title, "prop": "text", "format": "json"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "parse" not in payload:
        raise ValueError(f"Unexpected fandom payload for {page}: {payload}")

    html = payload["parse"]["text"]["*"]
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table")
    if table is None:
        raise ValueError(f"Cannot find playable table on {page}")

    rows: list[list[str]] = []
    for row in table.select("tr"):
        cells = row.find_all(["th", "td"])
        if not cells:
            continue
        rows.append([cell.get_text(" ", strip=True) for cell in cells])
    return rows


def fetch_hakush_data(api_url: str) -> Dict[str, dict]:
    """Fetch Hakush API JSON.

    Args:
        api_url: Hakush API endpoint.

    Returns:
        Raw JSON dict.
    """
    response = requests.get(api_url, timeout=30)
    response.raise_for_status()
    return response.json()


def resolve_zzz_entry(name_en: str, index: Dict[str, dict]) -> dict | None:
    """Resolve ZZZ full name to Hakush entry.

    Args:
        name_en: Name from Agent/List.
        index: Normalized Hakush index.

    Returns:
        Matched Hakush entry or None.
    """
    alias = ZZZ_NAME_ALIAS.get(name_en, name_en)
    candidates = [alias, name_en, name_en.split(" ")[0], name_en.split(" ")[-1]]
    for candidate in candidates:
        key = normalize_key(candidate)
        if key in index:
            return index[key]
    return None


def build_genshin_rows() -> list[dict]:
    """Build playable Genshin character rows."""
    fandom_rows = fetch_fandom_table(GENSHIN_PAGE)
    hakush_data = fetch_hakush_data(GENSHIN_API)

    hakush_index = {}
    traveler_entry = None
    for entry in hakush_data.values():
        hakush_index[normalize_key(entry["EN"])] = entry
        if entry["EN"] == "Traveler" and traveler_entry is None:
            traveler_entry = entry

    output_rows: list[dict] = []
    for cells in fandom_rows[1:]:
        if len(cells) < 6:
            continue
        name_en = cells[1]
        entry = hakush_index.get(normalize_key(name_en))
        if entry is None and name_en == "Traveler":
            entry = traveler_entry

        aliases = ""
        if name_en == "Traveler":
            aliases = "Aether|Lumine|空|荧"

        output_rows.append(
            {
                "id": f"genshin_{slugify(name_en)}",
                "game": "genshin_impact",
                "canonical_name_zh": entry["CHS"] if entry else "",
                "canonical_name_en": name_en,
                "aliases": aliases,
                "element": cells[3],
                "weapon": cells[4],
                "rarity": (map_genshin_rarity(entry["rank"]) if entry else ""),
                "release_date": (entry["release"][:10] if entry else ""),
                "source": GENSHIN_PAGE,
            }
        )
    return output_rows


def build_zzz_rows() -> list[dict]:
    """Build playable ZZZ agent rows."""
    fandom_rows = fetch_fandom_table(ZZZ_PAGE)
    hakush_data = fetch_hakush_data(ZZZ_API)

    hakush_index = {}
    for entry in hakush_data.values():
        hakush_index[normalize_key(entry["EN"])] = entry
        hakush_index[normalize_key(entry["code"])] = entry

    output_rows: list[dict] = []
    for cells in fandom_rows[1:]:
        if len(cells) < 8:
            continue
        name_en = cells[1]
        entry = resolve_zzz_entry(name_en, hakush_index)
        alias_candidates = [name_en]
        if entry:
            alias_candidates.extend([entry["EN"], entry["code"]])
        aliases = build_aliases(alias_candidates)

        output_rows.append(
            {
                "id": f"zzz_{slugify(name_en)}",
                "game": "zenless_zone_zero",
                "canonical_name_zh": entry["CHS"] if entry else "",
                "canonical_name_en": name_en,
                "aliases": aliases,
                "attribute": cells[3],
                "specialty": cells[4],
                "attack_type": cells[5],
                "faction": cells[6],
                "rarity": (map_zzz_rarity(entry["rank"]) if entry else ""),
                "release_date": parse_zzz_release_date(cells[7]),
                "source": ZZZ_PAGE,
            }
        )
    return output_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    """Write rows into UTF-8 CSV.

    Args:
        path: Output path.
        rows: Row dictionaries.
    """
    if not rows:
        raise ValueError(f"No rows to write: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Generate both character libraries and summary metadata."""
    genshin_rows = build_genshin_rows()
    zzz_rows = build_zzz_rows()

    write_csv(GENSHIN_OUTPUT, genshin_rows)
    write_csv(ZZZ_OUTPUT, zzz_rows)

    readme = OUTPUT_DIR / "README.md"
    generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    readme.write_text(
        (
            "# 角色库（原神 / 绝区零）\n\n"
            f"- 生成时间: {generated_at}\n"
            "- 数据来源:\n"
            f"  - {GENSHIN_PAGE}\n"
            f"  - {ZZZ_PAGE}\n"
            f"  - {GENSHIN_API}\n"
            f"  - {ZZZ_API}\n"
            "- 文件说明:\n"
            "  - genshin_impact_characters.csv: 原神可玩角色（按 Character/List 第一张表）\n"
            "  - zenless_zone_zero_agents.csv: 绝区零可用 Agent（按 Agent/List 第一张表）\n"
            "- 备注: 仅包含当前可玩角色，不包含 Upcoming 列表。\n"
        ),
        encoding="utf-8",
    )

    print(f"Genshin rows: {len(genshin_rows)}")
    print(f"ZZZ rows: {len(zzz_rows)}")


if __name__ == "__main__":
    main()

"""Fetch notable people from Wikipedia categories and save as notable_people.txt.

Run with: uv run python -m pii_proxy.gen_notable
"""
import httpx
import time
from pathlib import Path

URL = "https://en.wikipedia.org/w/api.php"
HEADERS = {
    "User-Agent": "pii-llm-proxy/1.0 (https://github.com/codedthinking/pii-llm-proxy; koren@ceu.edu)"
}

# Categories to crawl (depth 1 = include subcategories)
SEED_CATEGORIES = [
    # Science
    "Category:Nobel_laureates",
    "Category:Fellows_of_the_Econometric_Society",
    "Category:Members_of_the_United_States_National_Academy_of_Sciences",
    "Category:Fields_Medalists",
    "Category:Turing_Award_laureates",
    "Category:Fellows_of_the_Royal_Society",
    "Category:Members_of_the_French_Academy_of_Sciences",
    # Economics
    "Category:21st-century_American_economists",
    "Category:20th-century_American_economists",
    "Category:Keynesian_economists",
    "Category:Labor_economists",
    "Category:Development_economists",
    # Tech
    "Category:American_computer_scientists",
    "Category:British_computer_scientists",
    "Category:Free_software_programmers",
    "Category:R_(programming_language)_people",
    "Category:Python_(programming_language)_people",
    "Category:American_technology_chief_executives",
    "Category:American_technology_company_founders",
    "Category:Indian-American_chief_executives",
    "Category:Artificial_intelligence_researchers",
    "Category:Google_employees",
    "Category:Microsoft_employees",
    "Category:Apple_Inc._employees",
    "Category:Meta_Platforms_people",
    "Category:OpenAI_people",
    "Category:Nvidia_people",
    # Business
    "Category:American_billionaires",
    "Category:Chinese_billionaires",
    "Category:Indian_billionaires",
    "Category:Russian_billionaires",
    "Category:British_billionaires",
    "Category:Forbes_list_of_billionaires",
    # Politics - heads of state
    "Category:Presidents_of_the_United_States",
    "Category:Prime_Ministers_of_the_United_Kingdom",
    "Category:Chancellors_of_Germany",
    "Category:Presidents_of_France",
    "Category:Prime_Ministers_of_Hungary",
    "Category:Presidents_of_Russia",
    "Category:Prime_Ministers_of_India",
    "Category:Presidents_of_China",
    "Category:General_Secretaries_of_the_Chinese_Communist_Party",
    "Category:Prime_Ministers_of_Japan",
    "Category:Prime_Ministers_of_Canada",
    "Category:Prime_Ministers_of_Australia",
    "Category:Presidents_of_Brazil",
    "Category:21st-century_heads_of_state",
    # Journalists & media
    "Category:American_journalists",
    "Category:British_journalists",
    # Arts
    "Category:Academy_Award_winners",
    "Category:Grammy_Award_winners",
    "Category:Pulitzer_Prize_winners",
    "Category:Booker_Prize_winners",
    "Category:Emmy_Award_winners",
    "Category:Golden_Globe_Award_winners",
    # Sports
    "Category:Olympic_gold_medalists",
    "Category:FIFA_World_Cup-winning_players",
    "Category:NBA_All-Stars",
    "Category:World_chess_champions",
]


def get_category_members(category: str, cmtype: str = "page") -> list[str]:
    """Get all members of a Wikipedia category."""
    members = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
            "cmtype": cmtype,
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        resp = httpx.get(URL, params=params, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            time.sleep(2)
            continue
        try:
            data = resp.json()
        except Exception:
            time.sleep(2)
            continue
        for m in data["query"]["categorymembers"]:
            members.append(m["title"])
        if "continue" in data:
            cmcontinue = data["continue"]["cmcontinue"]
        else:
            break
        time.sleep(0.1)  # Be polite
    return members


def crawl_category(category: str, depth: int = 1) -> set[str]:
    """Get pages from a category, optionally recursing into subcategories."""
    names = set()
    pages = get_category_members(category, "page")
    for p in pages:
        if p.startswith("Category:"):
            continue
        # Strip disambiguation suffixes like "(politician)"
        if "(" in p:
            p = p[:p.index("(")].strip()
        if p:
            names.add(p)

    if depth > 0:
        subcats = get_category_members(category, "subcat")
        for subcat in subcats:
            names |= crawl_category(subcat, depth - 1)
    return names


def main():
    all_names = set()
    for cat in SEED_CATEGORIES:
        t0 = time.time()
        names = crawl_category(cat, depth=1)
        dt = time.time() - t0
        all_names |= names
        print(f"  {cat}: +{len(names)} ({dt:.1f}s) total={len(all_names)}")

    # Filter: only keep names that look like person names (2+ words, capitalized)
    filtered = set()
    for name in all_names:
        parts = name.split()
        if len(parts) >= 2 and all(p[0].isupper() for p in parts if p not in ("de", "von", "van", "di", "el", "al", "bin", "ibn", "der", "la", "le", "du")):
            filtered.add(name)

    # Manually add high-profile people missed by category crawling
    manual = {
        "Narendra Modi", "Recep Tayyip Erdogan", "Volodymyr Zelenskyy",
        "Rishi Sunak", "Keir Starmer", "Fumio Kishida", "Shigeru Ishiba",
        "Lula da Silva", "Javier Milei", "Giorgia Meloni",
        "Pedro Sánchez", "Olaf Scholz", "Justin Trudeau",
        "Pope Francis", "Dalai Lama",
    }
    filtered |= manual

    out = Path(__file__).parent / "notable_people.txt"
    out.write_text("\n".join(sorted(filtered)) + "\n")
    print(f"\nWrote {len(filtered)} notable people to {out}")


if __name__ == "__main__":
    main()

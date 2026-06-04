"""Generate names.txt from Faker's name pools across multiple locales."""
from pathlib import Path
import importlib

LOCALES = [
    "en_US",
    "de_DE", "de_AT", "de_CH",
    "it_IT",
    "fr_FR",
    "es_ES", "es_MX",
    "ru_RU",
    "hu_HU",
]

ATTRS = (
    "first_names", "first_names_female", "first_names_male",
    "last_names",
    "prefixes_female", "prefixes_male",
)

names = set()
for locale in LOCALES:
    try:
        mod = importlib.import_module(f"faker.providers.person.{locale}")
        provider = mod.Provider
    except (ImportError, AttributeError):
        print(f"  skipping {locale}")
        continue
    count = 0
    for attr in ATTRS:
        data = getattr(provider, attr, None)
        if data:
            if isinstance(data, dict):
                for k in data:
                    names.add(k.lower())
                    count += 1
            elif isinstance(data, (list, tuple)):
                for n in data:
                    names.add(n.lower())
                    count += 1
    print(f"  {locale}: {count} entries")

# Common prefixes/suffixes
names.update(["mr", "mrs", "ms", "dr", "jr", "sr", "phd", "md", "dds", "dvm"])

out = Path(__file__).parent / "names.txt"
out.write_text("\n".join(sorted(names)) + "\n")
print(f"Wrote {len(names)} names to {out}")

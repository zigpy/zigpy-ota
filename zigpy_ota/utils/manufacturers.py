"""Manufacturer mappings and utilities."""

from __future__ import annotations

# TODO: include other manufacturer IDs and names?
# https://github.com/SiliconLabs/simplicity_sdk/blob/sisdk-2025.6/app/zcl/manufacturers.xml
MANUFACTURER_ID_MAPPING: dict[int, str] = {
    0x100B: "Signify",
    0x1015: "Develco",
    0x1021: "Legrand",
    0x10E0: "Chameleon",
    0x10F2: "Ubisys",
    0x1105: "Bega",
    0x110C: "Ledvance",
    0x1124: "Jasco",
    0x1135: "Dresden Elektronik",
    0x1141: "Telink",
    0x1144: "Lutron",
    0x115F: "Lumi",
    0x1160: "Sengled",
    0x1166: "Innr",
    0x117A: "Insta",
    0x117C: "IKEA",
    0x1189: "Ledvance",
    0x1209: "Bosch",
    0x120B: "Heiman",
    0x121C: "Aurora",
    0x122F: "Inovelli",
    0x1233: "Third Reality",
    0x1246: "Danfoss",
    0x124F: "Gledopto",
    0x125F: "Niko",
    0x1286: "Sonoff",
    0x128B: "NodOn",
    0x130D: "Third Reality",
    0x1310: "Aeotec",
    0x1337: "Datek",
    0x1407: "Third Reality",
    0x2794: "Climax Technology",
}


def slugify_manufacturer(manufacturer_name: str) -> str:
    """Convert manufacturer name to a slug for directory naming."""
    return manufacturer_name.lower().replace(" ", "_")


# Valid manufacturer slugs derived from the mapping
# TODO: Seems to be unused currently, remove or use?
VALID_MANUFACTURER_SLUGS: set[str] = {
    slugify_manufacturer(name) for name in MANUFACTURER_ID_MAPPING.values()
}

# Mapping from both fancy names and slugs to slugified version
MANUFACTURER_NAME_TO_SLUG: dict[str, str] = {
    # Fancy names (lowercase for case-insensitive matching)
    name.lower(): slugify_manufacturer(name)
    for name in MANUFACTURER_ID_MAPPING.values()
} | {
    # Slugified names (map to themselves)
    slugify_manufacturer(name): slugify_manufacturer(name)
    for name in MANUFACTURER_ID_MAPPING.values()
}

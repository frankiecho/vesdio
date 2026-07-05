# src/providers/exiobase_config.py
"""
EXIOBASE-specific static configuration: region code -> name mapping, ISO3
codes for choropleth maps, and region groupings for the "shock a whole
region" UX.

This used to live in src/config.py. It was moved here as part of Workstream
5 (swappable IO-database core) so that src/config.py can stay generic
(design tokens / color palette only) while each MRIOProvider owns its own
region/sector vocabulary. src/config.py re-exports these names for backward
compatibility — existing `from src.config import country_mapping, ...`
imports (e.g. in app.py) keep working unchanged.
"""

# Mapping from 2-letter country codes to full names
country_mapping = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CY": "Cyprus", "CZ": "Czechia",
    "DE": "Germany", "DK": "Denmark", "EE": "Estonia", "ES": "Spain", "FI": "Finland",
    "FR": "France", "GR": "Greece", "HR": "Croatia", "HU": "Hungary", "IE": "Ireland",
    "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia", "MT": "Malta",
    "NL": "Netherlands", "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SE": "Sweden",
    "SI": "Slovenia", "SK": "Slovakia", "GB": "United Kingdom", "US": "United States",
    "JP": "Japan", "CN": "China", "CA": "Canada", "KR": "South Korea", "BR": "Brazil",
    "IN": "India", "MX": "Mexico", "RU": "Russia", "AU": "Australia", "CH": "Switzerland",
    "TR": "Turkey", "TW": "Taiwan", "NO": "Norway", "ID": "Indonesia", "ZA": "South Africa",
    'WA': 'Rest of Asia and Pacific', 'WL': 'Rest of America', 'WE': 'Rest of Europe',
    'WF': 'Rest of Africa', 'WM': 'Rest of Middle East'
}

# Mapping from 2-letter to 3-letter ISO country codes for choropleth map
COUNTRY_CODES_3_LETTER = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU",
    "DK": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN", "FR": "FRA", "GR": "GRC",
    "HR": "HRV", "HU": "HUN", "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX",
    "LV": "LVA", "MT": "MLT", "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU",
    "SE": "SWE", "SI": "SVN", "SK": "SVK", "GB": "GBR", "US": "USA", "JP": "JPN",
    "CN": "CHN", "CA": "CAN", "KR": "KOR", "BR": "BRA", "IN": "IND", "MX": "MEX",
    "RU": "RUS", "AU": "AUS", "CH": "CHE", "TR": "TUR", "TW": "TWN", "NO": "NOR",
    "ID": "IDN", "ZA": "ZAF"
}

# Groupings for aggregated regions for shock scenarios
REGION_GROUPS = {
    'EU27': [
        "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
        "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
        "NL", "PL", "PT", "RO", "SE", "SI", "SK"
    ],
    'OECD': [
        "AU", "AT", "BE", "CA", "CH", "CZ", "DE", "DK", "EE", "ES",
        "FI", "FR", "GR", "HU", "IE", "IT", "JP", "KR", "LT", "LU",
        "LV", "MX", "NL", "NO", "PL", "PT", "SE", "SI", "SK", "TR",
        "GB", "US"
    ],
    'Africa': ["ZA", "WF"],
    'Americas': ["US", "CA", "BR", "MX", "WL"],
    'Asia-Pacific': ["JP", "CN", "KR", "IN", "AU", "TW", "ID", "WA"],
    'Europe (Non-EU27)': ["GB", "CH", "NO", "RU", "WE"],
    'Middle East': ["WM"]
}


def get_valid_region_groups(all_countries):
    """Filter groups to only include valid countries for a given year's dataset."""
    valid_groups = {}
    for group_name, member_list in REGION_GROUPS.items():
        valid_members = [country for country in member_list if country in all_countries]
        if valid_members:
            valid_groups[group_name] = valid_members
    return valid_groups

# src/config.py

# This file contains static configuration data for the application.

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

# Color Palette for consistent styling across all charts
# Okabe-Ito colorblind-friendly palette
COLOR_PALETTE = {
    'blue': "#0072B2",      # Neutral/Base color (Okabe-Ito Blue)
    'red': "#D55E00",       # Impact/Negative color (Okabe-Ito Vermillion)
    'amber': "#E69F00",     # Highlight color for scales (Okabe-Ito Orange)
    'beige': "#F0E442",     # Secondary highlight for scales (Okabe-Ito Yellow)
    'green': "#009E73",      # Positive change color (Okabe-Ito Bluish Green)
    'grey': "#999999",      # For "Others" category (Grey)
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

# Filter groups to only include valid countries for a given year's dataset
def get_valid_region_groups(all_countries):
    valid_groups = {}
    for group_name, member_list in REGION_GROUPS.items():
        valid_members = [country for country in member_list if country in all_countries]
        if valid_members:
            valid_groups[group_name] = valid_members
    return valid_groups
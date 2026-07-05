# src/design_tokens.py
#
# Single source of truth for VESDIO's design tokens (Python side).
# Mirrors assets/design-system.css — keep both files in sync; see
# src/technical_documentation.md for the full reference and usage rules.
#
# `COLORS['brand']` holds the Okabe-Ito colorblind-safe palette that
# src/config.py's COLOR_PALETTE is derived from; do not alter those hexes.

COLORS = {
    # Okabe-Ito brand palette (colorblind-safe). Do not alter these hexes.
    "brand": {
        "blue": "#0072B2",
        "red": "#D55E00",
        "amber": "#E69F00",
        "beige": "#F0E442",
        "green": "#009E73",
        "grey": "#999999",
    },
    # Semantic aliases onto the brand palette above.
    "semantic": {
        "accent": "#0072B2",     # Okabe-Ito Blue
        "negative": "#D55E00",   # Okabe-Ito Vermillion
        "positive": "#009E73",   # Okabe-Ito Bluish Green
        "warning": "#E69F00",    # Okabe-Ito Orange
        "highlight": "#F0E442",  # Okabe-Ito Yellow
        "neutral": "#999999",    # Okabe-Ito Grey
    },
    # 9-step neutral ramp, replaces ad-hoc greys (#f0f0f0/#ddd/#ccc/#888/#f9f9f9).
    "grey": {
        100: "#F7F7F7",
        200: "#EEEEEE",
        300: "#E0E0E0",
        400: "#CCCCCC",
        500: "#999999",
        600: "#757575",
        700: "#555555",
        800: "#333333",
        900: "#1A1A1A",
    },
    # Theme surfaces (light mode values; dark-mode equivalents live in the CSS
    # file only, since Plotly figures always render on a fixed light canvas).
    "surface": {
        "bg": "#FFFFFF",
        "bg_subtle": "#F7F7F7",
        "surface": "#FFFFFF",
        "surface_raised": "#FFFFFF",
        "border": "#E0E0E0",
        "border_strong": "#CCCCCC",
        "text": "#1A1A1A",
        "text_muted": "#555555",
        "text_on_accent": "#FFFFFF",
    },
}

# Spacing scale — 4px base.
SPACING = {
    1: "4px",
    2: "8px",
    3: "12px",
    4: "16px",
    5: "20px",
    6: "24px",
    8: "32px",
    10: "40px",
    12: "48px",
    16: "64px",
}

# Radii.
RADII = {
    "sm": "2px",
    "md": "4px",
    "lg": "8px",
    "xl": "16px",
    "full": "9999px",
}

# Type scale.
TYPE = {
    "font_family_base": (
        "-apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, Helvetica, "
        "Arial, sans-serif"
    ),
    "font_family_mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    "font_size": {
        "xs": "0.75rem",
        "sm": "0.875rem",
        "base": "1rem",
        "md": "1.125rem",
        "lg": "1.25rem",
        "xl": "1.5rem",
        "2xl": "1.875rem",
        "3xl": "2.25rem",
    },
    "font_weight": {
        "normal": 400,
        "medium": 500,
        "bold": 700,
    },
    "line_height": {
        "tight": 1.2,
        "normal": 1.5,
        "relaxed": 1.75,
    },
}

# Elevation / shadow (light-mode values; dark-mode equivalents live in CSS).
SHADOWS = {
    "sm": "0 1px 2px rgba(26, 26, 26, 0.08)",
    "md": "0 2px 8px rgba(26, 26, 26, 0.12)",
    "lg": "0 8px 24px rgba(26, 26, 26, 0.16)",
    "xl": "0 16px 48px rgba(26, 26, 26, 0.20)",
}

# Z-index scale.
ZINDEX = {
    "base": 0,
    "dropdown": 1000,
    "sticky": 1100,
    "modal_backdrop": 1200,
    "modal": 1300,
    "popover": 1400,
    "tooltip": 1500,
    "toast": 1600,
}

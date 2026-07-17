import dash
from dash import dcc, html
import dash.exceptions
from dash.dependencies import Input, Output, State
import dash_mantine_components as dmc
import plotly.graph_objects as go
import numpy as np
from functools import lru_cache
import pandas as pd
import yaml
import base64
import io
import webbrowser
import sys
import os
from threading import Timer, Thread

from src.data_loader import load_labels_data, load_mrio_matrices, load_production_history, load_encore_materiality
from src.callbacks import handle_simulation_results
from src.plotting import create_builder_historical_plot
from src.config import country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE, get_valid_region_groups
from src.es_shock import effective_magnitude, extract_sector_intensities
from src.scenario_modeler import constrained_lp_would_fallback
from src.design_tokens import COLORS, SPACING, TYPE

# --- 1. Load Data and Pre-compute --- #
# Data will be loaded within the callback based on the selected year

# --- 2. Initialize Dash App --- #
# The CodePen skeleton stylesheet is gone: assets/design-system.css (WS0 tokens)
# is auto-served from assets/, and dash-mantine-components ships its own CSS
# bundled with the components (no external stylesheet needed as of dmc>=1.2).
app = dash.Dash(__name__,
    suppress_callback_exceptions=True,
)
server = app.server


def build_mantine_theme():
    """Builds a Mantine theme dict from the shared design tokens (src/design_tokens.py)
    so the component library and the hand-written CSS/Plotly colors never drift.

    Mantine expects each named color as a 10-shade array. Our brand tokens are
    flat (colorblind-safe Okabe-Ito) hexes rather than shade ramps, so we repeat
    the hex across the array — this keeps the exact brand color while still
    giving Mantine a valid palette to key off of (e.g. `primaryColor`).
    """
    brand = COLORS['brand']

    def shades(hex_color):
        return [hex_color] * 10

    return {
        "primaryColor": "vesdioBlue",
        "colors": {
            "vesdioBlue": shades(brand['blue']),
            "vesdioRed": shades(brand['red']),
            "vesdioGreen": shades(brand['green']),
            "vesdioAmber": shades(brand['amber']),
        },
        "fontFamily": TYPE['font_family_base'],
        "defaultRadius": "sm",
    }


MANTINE_THEME = build_mantine_theme()

# --- 3. Define App Layout --- #
# Define dropdown styles
dropdown_style = {
    'lineHeight': '1.4',
    'maxHeight': '400px',
    'minHeight': '38px'
}

# Style for the small scrollable "current items" lists (portfolio/scenario).
scroll_list_style = {
    'maxHeight': '150px',
    'overflowY': 'auto',
    'border': '1px solid var(--color-border)',
    'borderRadius': 'var(--radius-md)',
    'padding': SPACING[3],
    'backgroundColor': 'var(--color-bg-subtle)',
    'marginTop': SPACING[1],
}

years = list(range(1995, 2022))


def step_card(step_number, title, children, card_id=None):
    """A single step in the guided control-column flow: a numbered badge + title
    over a card of controls. `card_id` lets the paginated stepper show/hide it."""
    return dmc.Paper(
        id=card_id,
        withBorder=True,
        radius="md",
        p=SPACING[4],
        mb=SPACING[5],
        className='control-group',
        children=[
            dmc.Group(
                gap=SPACING[2],
                mb=SPACING[3],
                children=[
                    dmc.Badge(str(step_number), circle=True, color="vesdioBlue", variant="filled"),
                    dmc.Title(title, order=3, style={'margin': 0}),
                ]
            ),
            html.Div(children=children),
        ]
    )


# --- Top menu bar --- #
top_bar = html.Header(
    id='app-top-bar',
    style={
        'backgroundColor': 'var(--color-bg-subtle)',
        'borderBottom': '1px solid var(--color-border)',
        'padding': f"{SPACING[3]} {SPACING[8]}",
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'space-between',
        'flexShrink': 0,
    },
    children=[
        html.Div(style={'display': 'flex', 'alignItems': 'center', 'gap': SPACING[4]}, children=[
            html.Img(
                src='/assets/ms-icon-310x310.png',
                alt='VESDIO logo',
                style={'height': '48px'}
            ),
            dmc.Title("VESDIO", order=1, style={'margin': 0, 'fontSize': TYPE['font_size']['xl']}),
        ]),
        dmc.Button(
            "Instructions",
            id="open-instructions-button",
            n_clicks=0,
            variant="light",
            **{'aria-label': 'Open instructions and methodology'}
        )
    ]
)

# --- Step 1: Position / Portfolio --- #
position_step = step_card(1, "Your Position / Portfolio", [
    html.Fieldset(style={'border': 'none', 'padding': 0, 'margin': 0}, children=[
        html.Legend("Choose single asset or portfolio mode", className='visually-hidden'),
        dcc.RadioItems(
            id='position-mode-toggle',
            options=[
                {'label': 'Single Asset', 'value': 'single'},
                {'label': 'Portfolio', 'value': 'portfolio'},
            ],
            value='single',
            labelStyle={'display': 'inline-block', 'marginRight': SPACING[2]},
        ),
    ]),
    # Single Asset Mode Controls
    html.Div(id='single-asset-controls', children=[
        html.Label("Select Your Home Region:", htmlFor='home-region-dropdown', style={'marginTop': SPACING[2], 'display': 'block'}),
        dcc.Dropdown(id='home-region-dropdown', style=dropdown_style),
        html.Label("Select Your Home Sector:", htmlFor='home-sector-dropdown', style={'marginTop': SPACING[2], 'display': 'block'}),
        dcc.Dropdown(id='home-sector-dropdown', style=dropdown_style),
    ]),
    # Portfolio Mode Controls
    html.Div(id='portfolio-controls', style={'display': 'none'}, children=[
        html.Div(children=[
            html.Label("Region:", htmlFor='portfolio-region-select'),
            dcc.Dropdown(id='portfolio-region-select')
        ]),
        html.Div(children=[
            html.Label("Sector:", htmlFor='portfolio-sector-select'),
            dcc.Dropdown(id='portfolio-sector-select')
        ]),
        html.Label("Portfolio Weight (%):", htmlFor='portfolio-weight-input'),
        dcc.Input(id='portfolio-weight-input', type='number', min=0.1, max=100, step=0.1, value=10, style={'width': '100%'}),
        dmc.Button("Add to Portfolio", id="add-portfolio-item-button", n_clicks=0, fullWidth=True, mt=SPACING[2]),
        html.Div(id='portfolio-summary-display', style={'marginTop': SPACING[4]}),
        html.Div(id='portfolio-display-list', style=scroll_list_style),
        dmc.Grid(mt=SPACING[2], children=[
            dmc.GridCol(span=6, children=[
                dcc.Upload(
                    id='upload-portfolio',
                    children=dmc.Button('Import Portfolio', variant="default", fullWidth=True),
                    multiple=False, accept='.yaml,.yml'
                )
            ]),
            dmc.GridCol(span=6, children=[
                dmc.Button("Export Portfolio", id="export-portfolio-button", n_clicks=0, variant="default", fullWidth=True)
            ]),
        ]),
    ]),
], card_id='step-card-1')

# --- Step 2: Define Shock Event --- #
shock_step = step_card(2, "Define Shock Event", [
    html.Div(id='single-shock-controls', children=[
        html.Label("Shocked Region:", htmlFor='shock-region-dropdown', style={'marginTop': SPACING[2], 'display': 'block'}),
        dcc.Dropdown(id='shock-region-dropdown', style=dropdown_style),
        html.Fieldset(style={'border': 'none', 'padding': 0, 'margin': 0}, children=[
            html.Legend("Choose shock type", className='visually-hidden'),
            dcc.RadioItems(
                id='shock-type-toggle',
                options=[
                    {'label': 'Sector-Specific Shock', 'value': 'sector'},
                    {'label': 'Ecosystem Service Shock', 'value': 'ecosystem'},
                ],
                value='ecosystem',
                labelStyle={'display': 'inline-block', 'marginRight': SPACING[2]},
            ),
        ]),
        html.Div(id='sector-shock-controls', children=[
            html.Label("Shocked Sector:", htmlFor='shock-sector-dropdown', style={'marginTop': SPACING[2], 'display': 'block'}),
            dcc.Dropdown(id='shock-sector-dropdown', style=dropdown_style),
        ]),
        html.Div(id='ecosystem-shock-controls', style={'display': 'none'}, children=[
            html.Label("Ecosystem Service:", htmlFor='ecosystem-service-dropdown', style={'marginTop': SPACING[2], 'display': 'block'}),
            dcc.Dropdown(id='ecosystem-service-dropdown', style=dropdown_style),
        ]),
    ]),
    dmc.Divider(my=SPACING[3]),
    dmc.Button("Create Custom Scenario...", id='open-builder-button', n_clicks=0, variant="default", fullWidth=True),
    html.Div(id='builder-display-area', style={'display': 'none'}, children=[
        html.Label("Custom Scenario Shocks:", style={'marginTop': SPACING[2], 'display': 'block'}),
        html.Div(id='main-scenario-display-list', style=scroll_list_style),
        dmc.Grid(mt=SPACING[2], children=[
            dmc.GridCol(span=6, children=[
                dmc.Button("Edit Scenario...", id='edit-builder-button', n_clicks=0, variant="default", fullWidth=True)
            ]),
            dmc.GridCol(span=6, children=[
                dmc.Button("Clear Scenario", id='clear-scenario-button', n_clicks=0, color="vesdioRed", fullWidth=True)
            ]),
        ]),
    ]),
    dmc.Divider(my=SPACING[3]),
    html.Label("Shock Magnitude (%):", htmlFor='shock-magnitude-input', style={'display': 'block'}),
    dcc.Slider(
        id='shock-magnitude-input',
        min=0,
        max=100,
        step=1,
        value=10,
        marks={i: f'{i}%' for i in range(0, 101, 10)},
        tooltip={"placement": "bottom", "always_visible": True}
    ),
], card_id='step-card-2')

# --- Step 3: Configure --- #
configure_step = step_card(3, "Configure Simulation", [
    html.Label("Select Year:", htmlFor='year-dropdown', style={'marginTop': SPACING[2], 'display': 'block'}),
    dcc.Dropdown(
        id='year-dropdown',
        options=[{'label': str(y), 'value': y} for y in years],
        value=2021,
        style=dropdown_style
    ),
    html.Label("Calculation Method:", htmlFor='model-method-toggle', style={'marginTop': SPACING[2], 'display': 'block'}),
    dcc.RadioItems(
        id='model-method-toggle',
        options=[
            {'label': 'Leontief (Demand-Side)', 'value': 'leontief'},
            {'label': 'Ghosh (Supply-Side)', 'value': 'ghosh'},
            {'label': 'Constrained (Rigorous LP, slower)', 'value': 'constrained'},
        ],
        value='ghosh',
        labelStyle={'display': 'inline-block', 'marginRight': SPACING[2]},
    ),
], card_id='step-card-3')

# --- Run step (moved to the end of the guided flow) --- #
run_step = dmc.Paper(
    withBorder=True,
    radius="md",
    p=SPACING[4],
    className='control-group',
    children=[
        dmc.Button(
            '▶ Run Simulation',
            id='run-button',
            n_clicks=0,
            size="lg",
            fullWidth=True,
            color="vesdioBlue",
            **{'aria-label': 'Run the simulation with the configured scenario'}
        ),
        dmc.Text(
            id='run-button-error-message',
            **{'aria-live': 'polite'},
            style={'color': 'var(--color-negative)', 'textAlign': 'center', 'marginTop': SPACING[1], 'minHeight': '20px'}
        )
    ]
)

# Paginated step navigation: clicking a step in the rail shows only that
# step's card below, and each step gets a checkmark once its required
# fields are all filled in (tracked via step-validation-store).
guided_stepper = dmc.Stepper(
    id='ui-guided-stepper',
    active=0,
    allowNextStepsSelect=True,
    size="sm",
    color="vesdioBlue",
    mb=SPACING[5],
    children=[
        dmc.StepperStep(id='stepper-step-1', label="Position", description="Who are you?"),
        dmc.StepperStep(id='stepper-step-2', label="Shock", description="What happens?"),
        dmc.StepperStep(id='stepper-step-3', label="Configure", description="How severe?"),
    ]
)

step_validation_store = dcc.Store(id='step-validation-store', data={'step1': False, 'step2': False, 'step3': False})

left_column = dmc.Stack(
    gap=0,
    children=[
        guided_stepper,
        step_validation_store,
        position_step,
        shock_step,
        configure_step,
        run_step,
    ]
)

# --- Right column: results --- #
scenario_summary_header = dmc.Alert(
    id='scenario-summary-header',
    title="Scenario summary",
    color="vesdioBlue",
    variant="light",
    mb=SPACING[4],
    **{'aria-live': 'polite'}
)

results_empty_state = html.Div(
    id='results-empty-state',
    role='status',
    style={
        'textAlign': 'center',
        'padding': f"{SPACING[12]} {SPACING[4]}",
        'color': 'var(--color-text-muted)',
        'border': '1px dashed var(--color-border-strong)',
        'borderRadius': 'var(--radius-lg)',
    },
    children=[
        dmc.Title("No results yet", order=3, style={'margin': 0}),
        dmc.Text("Configure your position and shock event on the left, then click ▶ Run Simulation to see results here.", mt=SPACING[2]),
    ]
)

right_column = html.Div(children=[
    scenario_summary_header,
    results_empty_state,
    dcc.Loading(
        id="loading-results",
        type="default",
        parent_style={
            'minHeight': '90vh'
        },
        children=html.Div(id='results-output', style={'display': 'none'}, children=[
            html.H3(id='results-title', style={'textAlign': 'center'}),
            dcc.Tabs(id="results-tabs", children=[
                dcc.Tab(label='Summary', children=[
                    dmc.Grid(mt=SPACING[5], children=[
                        dmc.GridCol(span={"base": 12, "md": 6}, children=[dcc.Graph(id='home-impact-barchart', config={'responsive': True})]),
                        dmc.GridCol(span={"base": 12, "md": 6}, children=[dcc.Graph(id='impact-waterfall-chart', config={'responsive': True})]),
                    ]),
                    # Display Options
                    html.Div(className='control-group', style={'marginTop': SPACING[5]}, children=[
                        dmc.Title("Display Options", order=3),
                        html.Label("Aggregation Level:", style={'marginTop': SPACING[4], 'display': 'block'}),
                        dcc.RadioItems(
                            id='aggregation-toggle',
                            options=[
                                {'label': 'Show by Country-Sector', 'value': 'none'},
                                {'label': 'Aggregate by Country', 'value': 'country'},
                                {'label': 'Aggregate by Sector', 'value': 'sector'},
                            ],
                            value='country',
                            labelStyle={'display': 'block'}
                        ),
                    ]),
                ]),
                dcc.Tab(label='Geographic Impact', children=[
                    html.Div(style={'marginTop': SPACING[5]}, children=[
                        dcc.Graph(id='country-impact-chart', config={'responsive': True})
                    ])
                ]),
                dcc.Tab(label='Supply Chain Flow', children=[
                    html.Div(style={'marginTop': SPACING[5]}, children=[
                        dcc.Graph(id='sankey-diagram', config={'responsive': True})
                    ])
                ]),
                dcc.Tab(label='Global Impacts', children=[
                    html.Div([
                        html.Label("Rank Sectors By:", style={'fontWeight': 'bold'}),
                        dcc.RadioItems(
                            id='top-impacts-sort-toggle',
                            options=[
                                {'label': 'Relative Impact (%)', 'value': 'percentage'},
                                {'label': 'Absolute Impact (Monetary)', 'value': 'absolute'},
                            ],
                            value='percentage',
                            labelStyle={'display': 'inline-block', 'marginRight': SPACING[4]},
                        ),
                    ], style={'padding': SPACING[4]}),
                    html.Div(id='top-impacts-table'),
                ]),
                dcc.Tab(label='Historical Context', children=[
                    dcc.Graph(id='production-history-chart', config={'responsive': True})
                ]),
                dcc.Tab(label='Portfolio Breakdown', id='portfolio-breakdown-tab', children=[
                    html.Div(id='portfolio-breakdown-content', style={'padding': SPACING[5]})
                ]),
            ])
        ])
    ),
])

main_content = dmc.Container(
    fluid=True,
    style={'padding': SPACING[5], 'overflowY': 'auto', 'flexGrow': 1},
    children=[
        # These dcc.Store components hold shared scenario/portfolio state used by
        # multiple callbacks below; kept exactly as before (unchanged ids).
        dcc.Store(id='scenario-store', storage_type='memory', data=[]),
        dcc.Store(id='portfolio-store', storage_type='memory', data=[]),
        dcc.Store(id='encore-data-store', storage_type='memory'),

        dmc.Grid(gutter="lg", children=[
            dmc.GridCol(span={"base": 12, "md": 4}, children=[left_column]),
            dmc.GridCol(span={"base": 12, "md": 8}, style={'position': 'relative'}, children=[right_column]),
        ]),
    ]
)

# --- Scenario Builder Modal (dmc.Modal: focus trap + Esc-to-close built in) --- #
scenario_builder_modal = dmc.Modal(
    id="scenario-builder-modal",
    opened=False,
    withCloseButton=False,
    size="lg",
    zIndex=1300,
    children=[
        html.Div([
            dmc.Group(justify="space-between", children=[
                dmc.Title("Scenario Builder", order=2),
                dmc.ActionIcon(
                    "×",
                    id="modal-close-button",
                    n_clicks=0,
                    variant="subtle",
                    size="lg",
                    **{'aria-label': 'Close scenario builder'}
                ),
            ]),
        ]),
        html.Div([
            # --- Part 1: Add/Configure a single shock ---
            dmc.Title("1. Configure a Shock", order=4, mt=SPACING[4]),
            dmc.Grid(children=[
                dmc.GridCol(span={"base": 12, "md": 3}, children=[
                    html.Label("Region:", htmlFor='builder-region-select'),
                    dcc.Dropdown(id='builder-region-select')
                ]),
                dmc.GridCol(span={"base": 12, "md": 4}, children=[
                    html.Label("Sector:", htmlFor='builder-sector-select'),
                    dcc.Dropdown(id='builder-sector-select')
                ]),
                dmc.GridCol(span={"base": 12, "md": 3}, children=[
                    html.Label("Magnitude (%):"),
                    dcc.Slider(
                        id='builder-magnitude-input',
                        min=0, max=100, step=1, value=10,
                        marks={i: f'{i}%' for i in range(0, 101, 20)},
                        tooltip={"placement": "bottom", "always_visible": True}
                    )
                ]),
                dmc.GridCol(span={"base": 12, "md": 2}, children=[
                    dmc.Button("Add Shock", id="builder-add-shock-button", n_clicks=0, fullWidth=True, mt=SPACING[6])
                ]),
            ]),
            dcc.Loading(type="circle", children=dcc.Graph(id='builder-single-chart', style={'height': '300px'})),
            dmc.Divider(my=SPACING[3]),
            # --- Part 2: Review the cumulative scenario ---
            dmc.Title("2. Review Cumulative Scenario", order=4),
            dmc.Grid(children=[
                dmc.GridCol(span={"base": 12, "md": 6}, children=[
                    dmc.Title("Current Shocks List", order=5),
                    html.Div(id='scenario-display-list', style={
                        'maxHeight': '250px', 'overflowY': 'auto',
                        'border': '1px solid var(--color-border)', 'borderRadius': 'var(--radius-md)',
                        'padding': SPACING[3]
                    })
                ]),
                dmc.GridCol(span={"base": 12, "md": 6}, children=[
                    dcc.Loading(
                        type="circle",
                        children=dcc.Graph(id='builder-combined-chart', style={'height': '300px'})
                    )
                ])
            ])
        ]),
        # Footer
        dmc.Grid(mt=SPACING[5], children=[
            dmc.GridCol(span={"base": 12, "md": 6}, children=[
                dcc.Upload(
                    id='upload-yaml',
                    children=dmc.Button('Import from YAML', variant="default"),
                    multiple=False,
                    accept='.yaml,.yml'
                )
            ]),
            dmc.GridCol(span={"base": 12, "md": 6}, style={'textAlign': 'right'}, children=[
                dmc.Button("Export to YAML", id="export-yaml-button", n_clicks=0, variant="default"),
                dcc.Download(id="download-yaml"),
                dmc.Button("Save and Close", id="modal-save-button", n_clicks=0, ml=SPACING[2]),
            ])
        ])
    ]
)

# --- Instructions Modal --- #
instructions_modal = dmc.Modal(
    id="instructions-modal",
    opened=False,
    withCloseButton=False,
    size="lg",
    zIndex=1400,
    children=[
        dmc.Group(justify="space-between", children=[
            dmc.Title("How to Use VESDIO", order=2),
            dmc.ActionIcon(
                "×",
                id="instructions-modal-close-button",
                n_clicks=0,
                variant="subtle",
                size="lg",
                **{'aria-label': 'Close instructions'}
            ),
        ]),
        dcc.Markdown('''
            Welcome to the Valuing Ecosystem Service Dependencies with Input-Output (VESDIO) tool. This application helps you simulate the economic impacts of ecosystem services and supply chain disruptions.

            #### **Step 1: Set Your Perspective**
            In the "Your Position / Portfolio" panel, choose how you want to analyze impacts:
            - **Single Asset Mode**: This is the default. Select a single "Home Region" and "Home Sector" that represents your organization or area of interest. The results will be framed from this specific perspective.
            - **Portfolio Mode**: Switch to this mode to model a collection of assets.
                - Select a region, sector, and a weight (%) for each asset.
                - Click "Add to Portfolio". You can add multiple assets.
                - The total weight of all assets in your portfolio **must sum to 100%** before you can run the simulation.

            #### **Step 2: Define the Disruption**
            You can model a disruption in two ways:
            - **A) Single Shock**: Use the "Define Shock Event" panel to model a simple disruption.
                - **Sector-Specific**: Choose a region and a specific sector to disrupt (e.g., a 10% reduction in 'Cultivation of wheat' in 'Ukraine').
                - **Ecosystem Service Shock**: Choose a region and an ecosystem service (e.g., 'Water Supply' in 'Brazil'). The tool will automatically apply the shock to all sectors in that region that are highly dependent on that service.
            - **B) Custom Scenario**: For more complex events, click **"Create Custom Scenario..."**. This opens the Scenario Builder where you can add multiple shocks across different regions and sectors, each with its own magnitude. You can also import/export these scenarios as YAML files.

            #### **Step 3: Configure the Simulation**
            - **Year**: Select the dataset year for the underlying economic model.
            - **Calculation Method**: Choose between 'Ghosh (Supply-Side)' for supply shocks (default) or 'Leontief (Demand-Side)' for demand shocks.
            - **Shock Magnitude**: Use the slider to set the severity of the disruption (e.g., a 10% shock means the output of the shocked sector(s) is reduced by 10%).

            #### **Step 4: Run and Analyze**
            - Click the **"▶ Run Simulation"** button.
            - The results will appear on the right. Use the tabs to explore different views. In Portfolio Mode, the results are aggregated across all your assets.
                - **Summary**: Key impacts on your position/portfolio and a waterfall chart showing contributing factors.
                - **Geographic Impact**: A world map visualizing the global distribution of impacts.
                - **Supply Chain Flow**: A Sankey diagram illustrating the flow of the disruption through the supply chain.
                - **Global Impacts**: A table of the most affected sectors worldwide based on this supply chain disruption.
                - **Historical Context**: A chart showing the size of the impact relative to historical production.

            #### **Technical Note**

            The input-output models are based on EXIOBASE v3.9.6 (June 2025). It covers all 44 countries and 5 rest-of-world regions in EXIOBASE.

            EXIOBASE citation: Stadler, K., Wood, R., Bulavskaya, T., Södersten, C.-J., Simas, M., Schmidt, S., Usubiaga, A., Acosta-Fernández, J., Kuenen, J., Bruckner, M., Giljum, S., Lutter, S., Merciai, S., Schmidt, J. H., Theurl, M. C., Plutzar, C., Kastner, T., Eisenmenger, N., Erb, K.-H., … Tukker, A. (2025). EXIOBASE 3 (3.9.6) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.15689391

            The link between ecosystem services and sector production is calculated through materiality ratings in the ENCORE database. Sectors with "High" or "Very High" materiality to an ecosystem services are assumed to have production decreased in proportion to the specified magnitude of production disruption. Sectors without a "High" or "Very High" materiality rating to an ecosystem service is assumed to be unaffected.

            ENCORE citation: Global Canopy and UNEP (2025). Exploring Natural Capital Opportunities, Risk and Exposure (June 2025 update). https://encorenature.org/en

            #### Disclaimer

            This tool is in its experimental phase and is not yet fully tested and validated. It does not come with warranty. Use at your own risk.
        ''')
    ]
)

app.layout = dmc.MantineProvider(
    id='mantine-provider',
    theme=MANTINE_THEME,
    defaultColorScheme="auto",
    children=html.Div(
        id='app-root',
        style={
            'fontFamily': 'var(--font-family-base)',
            'minHeight': '100vh',
            'display': 'flex',
            'flexDirection': 'column',
            'backgroundColor': 'var(--color-bg)',
            'color': 'var(--color-text)',
        },
        children=[
            top_bar,
            main_content,
            scenario_builder_modal,
            instructions_modal,
            dcc.Download(id="download-portfolio-yaml"),
        ]
    )
)

# --- 4. Define Callback Logic --- #

@app.callback(
    [Output('home-region-dropdown', 'options'),
     Output('home-sector-dropdown', 'options'),
     Output('portfolio-region-select', 'options'),
     Output('portfolio-sector-select', 'options'),
     Output('shock-region-dropdown', 'options'),
     Output('builder-region-select', 'options'),
     Output('builder-sector-select', 'options'),
     Output('shock-sector-dropdown', 'options'),
     Output('ecosystem-service-dropdown', 'options'),
     Output('encore-data-store', 'data'),
     Output('home-region-dropdown', 'value'),
     Output('home-sector-dropdown', 'value'),
     Output('shock-region-dropdown', 'value'),
     Output('shock-sector-dropdown', 'value'),
     Output('ecosystem-service-dropdown', 'value')],
    [Input('year-dropdown', 'value')]
)
def update_dropdowns(year):
    LABELS, COUNTRIES, SECTORS, DEFAULTS = load_labels_data(year)

    # Create options for individual countries
    country_options = [{'label': country_mapping.get(c, c), 'value': c} for c in COUNTRIES]

    # Create options for aggregated regions
    valid_region_groups = get_valid_region_groups(COUNTRIES)
    group_options = [{'label': name, 'value': name} for name in sorted(valid_region_groups.keys())]

    # Combine options with separators for the shock dropdown
    shock_country_options = [
        {'label': 'Global', 'value': 'All'},
        {'label': '──────────', 'value': 'separator1', 'disabled': True},
    ] + group_options + [
        {'label': '──────────', 'value': 'separator2', 'disabled': True},
    ] + country_options

    # Sector options
    sector_options = [{'label': s, 'value': s} for s in SECTORS]

    # Add ecosystem services options for the dropdown
    encore_materiality = load_encore_materiality() or []
    ecosystem_services = sorted([item['service'] for item in encore_materiality])
    ecosystem_service_options = [{'label': s, 'value': s} for s in ecosystem_services]
    default_ecosystem_service = ecosystem_services[0] if ecosystem_services else None
    ecosystem_service_options = [{'label': s, 'value': s} for s in ecosystem_services]
    # Set the default ecosystem service to 'Pollination' if it exists, otherwise fallback.
    default_ecosystem_service = 'Pollination' if 'Pollination' in ecosystem_services else (ecosystem_services[0] if ecosystem_services else None)

    if DEFAULTS:
        default_home_region = DEFAULTS.get('home_region', COUNTRIES[0])
        default_home_sector = DEFAULTS.get('home_sector', SECTORS[0])
        default_shock_region = DEFAULTS.get('shock_region', COUNTRIES[1] if len(COUNTRIES) > 1 else COUNTRIES[0])
        default_home_sector = "Processing of Food products nec"
        # Default shock region is now 'All' for the global ecosystem shock
        default_shock_region = 'All'
        default_shock_sector = DEFAULTS.get('shock_sector', SECTORS[1] if len(SECTORS) > 1 else SECTORS[0])
    else:
        default_home_region = COUNTRIES[0]
        default_home_sector = SECTORS[0]
        default_shock_region = COUNTRIES[1] if len(COUNTRIES) > 1 else COUNTRIES[0]
        # Default shock region is now 'All' for the global ecosystem shock
        default_shock_region = 'All'
        default_shock_sector = SECTORS[1] if len(SECTORS) > 1 else SECTORS[0]

    return (country_options, sector_options, country_options, sector_options, shock_country_options, country_options,
            sector_options, sector_options, ecosystem_service_options, encore_materiality,
            default_home_region, default_home_sector, default_shock_region,
            default_shock_sector, default_ecosystem_service)

@app.callback(
    [Output('single-asset-controls', 'style'),
     Output('portfolio-controls', 'style')],
    [Input('position-mode-toggle', 'value')]
)
def toggle_position_mode(mode):
    """Switches between Single Asset and Portfolio input controls."""
    if mode == 'portfolio':
        return {'display': 'none'}, {'display': 'block'}
    else: # single
        return {'display': 'block'}, {'display': 'none'}

@app.callback(
    [Output('sector-shock-controls', 'style'),
     Output('ecosystem-shock-controls', 'style')],
    [Input('shock-type-toggle', 'value')]
)
def toggle_shock_controls(shock_type):
    if shock_type == 'ecosystem':
        return {'display': 'none'}, {'display': 'block'}
    return {'display': 'block'}, {'display': 'none'}

@app.callback(
    [Output('single-shock-controls', 'style'),
     Output('builder-display-area', 'style')],
    [Input('scenario-store', 'data')]
)
def toggle_shock_mode(scenario_data):
    """Shows/hides shock controls based on whether a custom scenario exists."""
    if scenario_data: # If the store has data, we are in builder mode
        return {'display': 'none'}, {'display': 'block'}
    # Default to single shock mode
    return {'display': 'block'}, {'display': 'none'}

# NOTE: the two modal-toggle callbacks below now target dmc.Modal's `opened`
# (boolean) prop instead of the old hand-rolled div's `style` dict — this is
# the one intentional signature change in this workstream, required to adopt
# the library Modal (built-in focus trap + Esc-to-close, per WS1 scope item 4).
# All modal-related component ids (scenario-builder-modal, modal-close-button,
# instructions-modal, instructions-modal-close-button, etc.) are unchanged.
@app.callback(
    Output('scenario-builder-modal', 'opened'),
    [Input('open-builder-button', 'n_clicks'),
     Input('edit-builder-button', 'n_clicks'),
     Input('modal-save-button', 'n_clicks'),
     Input('modal-close-button', 'n_clicks')],
    prevent_initial_call=True,
)
def toggle_modal(open_clicks, edit_clicks, save_clicks, close_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id in ['open-builder-button', 'edit-builder-button']:
        return True
    if trigger_id in ['modal-save-button', 'modal-close-button']:
        return False
    return dash.no_update

@app.callback(
    Output('instructions-modal', 'opened'),
    [Input('open-instructions-button', 'n_clicks'),
     Input('instructions-modal-close-button', 'n_clicks')],
    prevent_initial_call=True
)
def toggle_instructions_modal(open_clicks, close_clicks):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'open-instructions-button':
        return True
    if trigger_id == 'instructions-modal-close-button':
        return False
    return dash.no_update

@app.callback(
    Output('add-portfolio-item-button', 'disabled'),
    [Input('portfolio-weight-input', 'value'),
     Input('portfolio-store', 'data')],
    [State('portfolio-region-select', 'value'),
     State('portfolio-sector-select', 'value')]
)
def disable_add_to_portfolio_button(new_weight, portfolio_data, region, sector):
    """
    Disables the 'Add to Portfolio' button if the new item would cause the
    total weight to exceed 100%.
    """
    if new_weight is None or new_weight <= 0:
        return True # Disable if weight is invalid

    current_total_weight = sum(item.get('weight', 0) for item in portfolio_data)

    # Check if the item being added/edited already exists in the portfolio
    existing_item_weight = 0
    for item in portfolio_data:
        if item['region'] == region and item['sector'] == sector:
            existing_item_weight = item['weight']
            break

    # Calculate the potential new total weight
    # (Current total - old weight of item + new weight of item)
    potential_total = (current_total_weight - existing_item_weight) + new_weight

    return potential_total > 100

@app.callback(
    [Output('portfolio-store', 'data'),
     Output('portfolio-display-list', 'children'),
     Output('portfolio-summary-display', 'children')],
    [Input('add-portfolio-item-button', 'n_clicks'),
     Input({'type': 'delete-portfolio-item-button', 'index': dash.ALL}, 'n_clicks'),
     Input('upload-portfolio', 'contents')],
    [State('portfolio-region-select', 'value'),
     State('portfolio-sector-select', 'value'),
     State('portfolio-weight-input', 'value'),
     State('portfolio-store', 'data'),
     State('upload-portfolio', 'filename')]
)
def update_portfolio_store(add_clicks, delete_clicks, upload_contents, region, sector, weight, current_portfolio, filename):
    ctx = dash.callback_context
    trigger_id = ctx.triggered_id

    if isinstance(trigger_id, dict) and trigger_id.get('type') == 'delete-portfolio-item-button':
        item_index_to_delete = trigger_id['index']
        if 0 <= item_index_to_delete < len(current_portfolio):
            current_portfolio.pop(item_index_to_delete)
    elif trigger_id == 'add-portfolio-item-button' and region and sector and weight is not None:
        new_item = {'region': region, 'sector': sector, 'weight': weight}
        # Check if item exists to update it, otherwise append
        item_updated = False
        for item in current_portfolio:
            if item['region'] == region and item['sector'] == sector:
                item['weight'] = weight
                item_updated = True
                break
        if not item_updated:
            current_portfolio.append(new_item)
    elif trigger_id == 'upload-portfolio' and upload_contents is not None:
        try:
            content_type, content_string = upload_contents.split(',')
            decoded = base64.b64decode(content_string)
            uploaded_portfolio = yaml.safe_load(io.StringIO(decoded.decode('utf-8')))
            # Basic validation
            if isinstance(uploaded_portfolio, list) and all('region' in item and 'sector' in item and 'weight' in item for item in uploaded_portfolio):
                current_portfolio = uploaded_portfolio
        except Exception as e:
            print(f"Error parsing uploaded portfolio YAML: {e}")


    # Generate display list
    display_items = []
    total_weight = 0
    for i, item in enumerate(current_portfolio):
        total_weight += item['weight']
        region_name = country_mapping.get(item['region'], item['region'])
        display_items.append(html.Div([
            html.Span(f"• {item['weight']}%: {region_name} - {item['sector']}", style={'flexGrow': 1}),
            html.Button("×", id={'type': 'delete-portfolio-item-button', 'index': i}, n_clicks=0, style={'border': 'none', 'background': 'transparent', 'color': 'var(--color-negative)', 'fontWeight': 'bold', 'cursor': 'pointer'})
        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}))

    summary_text = f"Total Weight: {total_weight:.1f}%"
    summary_style = {'fontWeight': 'bold', 'color': 'var(--color-negative)' if not np.isclose(total_weight, 100) else 'var(--color-text)'}
    summary_display = html.P(summary_text, style=summary_style)

    return current_portfolio, display_items, summary_display

@app.callback(
    [Output('scenario-store', 'data'),
     Output('scenario-display-list', 'children'),
     Output('main-scenario-display-list', 'children')],
    [Input('builder-add-shock-button', 'n_clicks'),
     Input('clear-scenario-button', 'n_clicks'),
     Input({'type': 'delete-shock-button', 'index': dash.ALL}, 'n_clicks'),
     Input('upload-yaml', 'contents')],
    [State('builder-region-select', 'value'),
     State('builder-sector-select', 'value'),
     State('builder-magnitude-input', 'value'),
     State('scenario-store', 'data'),
     State('upload-yaml', 'filename')]
)
def update_scenario_store(add_clicks, clear_clicks, delete_clicks, upload_contents, region, sector, magnitude, current_shocks, filename):
    ctx = dash.callback_context
    trigger_id = ctx.triggered_id

    if trigger_id == 'clear-scenario-button':
        current_shocks = []
    elif isinstance(trigger_id, dict) and trigger_id.get('type') == 'delete-shock-button':
        # A specific delete button was clicked
        shock_index_to_delete = trigger_id['index']
        if 0 <= shock_index_to_delete < len(current_shocks):
            current_shocks.pop(shock_index_to_delete)
    elif trigger_id == 'builder-add-shock-button' and region and sector and magnitude is not None:
        # The add button was clicked
        # Check if the shock already exists and update it, otherwise add it.
        shock_updated = False
        for shock in current_shocks:
            if shock['region'] == region and shock['sector'] == sector:
                shock['magnitude'] = magnitude
                shock_updated = True
                break
        if not shock_updated:
            current_shocks.append({'region': region, 'sector': sector, 'magnitude': magnitude})
    elif upload_contents is not None:
        # A file was uploaded
        try:
            content_type, content_string = upload_contents.split(',')
            decoded = base64.b64decode(content_string)
            uploaded_shocks = yaml.safe_load(io.StringIO(decoded.decode('utf-8')))
            # Basic validation
            if isinstance(uploaded_shocks, list) and all('region' in s and 'sector' in s and 'magnitude' in s for s in uploaded_shocks):
                current_shocks = uploaded_shocks
        except Exception as e:
            print(f"Error parsing uploaded YAML file: {e}")

    # Generate the display list with delete buttons
    display_items = []
    for i, s in enumerate(current_shocks):
        region_name = country_mapping.get(s['region'], s['region'])
        display_items.append(html.Div([
            html.Span(f"• {region_name} - {s['sector']}: {s['magnitude']}%", style={'flexGrow': 1}),
            html.Button("×", id={'type': 'delete-shock-button', 'index': i}, n_clicks=0, style={'border': 'none', 'background': 'transparent', 'color': 'var(--color-negative)', 'fontWeight': 'bold', 'cursor': 'pointer'})
        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}))

    return current_shocks, display_items, display_items

@app.callback(
    [Output('run-button', 'disabled'),
     Output('run-button-error-message', 'children')],
    [Input('position-mode-toggle', 'value'),
     Input('portfolio-store', 'data'),
     Input('step-validation-store', 'data')]
)
def update_run_button_state_and_message(position_mode, portfolio_data, step_validation):
    """
    Disables the 'Run Simulation' button and shows an error message below it
    if in portfolio mode and the total weight is not exactly 100%, or if any
    of the three guided steps is not yet fully filled in.
    """
    if position_mode == 'portfolio':
        total_weight = sum(item.get('weight', 0) for item in portfolio_data)
        if not np.isclose(total_weight, 100):
            error_text = f"Portfolio weight must be 100% (is {total_weight:.1f}%)"
            return True, error_text  # Disable button and show error message

    step_validation = step_validation or {}
    if not all(step_validation.get(k) for k in ('step1', 'step2', 'step3')):
        return True, "Complete steps 1-3 to run the simulation"

    # In all other cases, enable the button and clear the error message
    return False, ""


@app.callback(
    Output('step-validation-store', 'data'),
    [Input('position-mode-toggle', 'value'),
     Input('home-region-dropdown', 'value'),
     Input('home-sector-dropdown', 'value'),
     Input('portfolio-store', 'data'),
     Input('shock-type-toggle', 'value'),
     Input('shock-region-dropdown', 'value'),
     Input('shock-sector-dropdown', 'value'),
     Input('ecosystem-service-dropdown', 'value'),
     Input('scenario-store', 'data'),
     Input('shock-magnitude-input', 'value'),
     Input('year-dropdown', 'value'),
     Input('model-method-toggle', 'value')]
)
def compute_step_validation(position_mode, home_region, home_sector, portfolio_data,
                             shock_type, shock_region, shock_sector, ecosystem_service,
                             scenario_data, magnitude, year, method):
    """Tracks whether each guided step's required fields are all filled in."""
    if position_mode == 'portfolio':
        total_weight = sum(item.get('weight', 0) for item in (portfolio_data or []))
        step1_valid = bool(portfolio_data) and np.isclose(total_weight, 100)
    else:
        step1_valid = bool(home_region) and bool(home_sector)

    if scenario_data:
        step2_valid = True
    elif shock_type == 'sector':
        step2_valid = bool(shock_region) and bool(shock_sector)
    else:
        step2_valid = bool(shock_region) and bool(ecosystem_service)
    step2_valid = step2_valid and magnitude is not None

    step3_valid = year is not None and bool(method)

    return {'step1': step1_valid, 'step2': step2_valid, 'step3': step3_valid}


@app.callback(
    [Output('stepper-step-1', 'icon'),
     Output('stepper-step-2', 'icon'),
     Output('stepper-step-3', 'icon')],
    Input('step-validation-store', 'data')
)
def update_stepper_ticks(step_validation):
    """Shows a checkmark on a step's badge once that step is fully validated."""
    step_validation = step_validation or {}
    return tuple(
        "✓" if step_validation.get(k) else None
        for k in ('step1', 'step2', 'step3')
    )


@app.callback(
    [Output('step-card-1', 'style'),
     Output('step-card-2', 'style'),
     Output('step-card-3', 'style')],
    Input('ui-guided-stepper', 'active')
)
def show_active_step_card(active):
    """Paginates the guided flow: only the card for the clicked/active step is shown."""
    active = active if active is not None else 0
    styles = [{'display': 'none'}] * 3
    if 0 <= active < 3:
        styles[active] = {'display': 'block'}
    else:
        styles = [{'display': 'block'}] * 3
    return styles


@app.callback(
    [Output('builder-single-chart', 'figure'),
     Output('builder-single-chart', 'style')],
    [Input('builder-region-select', 'value'),
     Input('builder-sector-select', 'value'),
     Input('builder-magnitude-input', 'value'),
     Input('year-dropdown', 'value')]
)
def update_builder_single_chart(region, sector, magnitude, year):
    """Updates the historical chart for the currently selected shock in the builder."""
    base_style = {'height': '300px'}
    if not all([region, sector, magnitude is not None, year]):
        return go.Figure(), {**base_style, 'display': 'none'}

    shock = [{'region': region, 'sector': sector, 'magnitude': magnitude}]
    history = load_production_history()
    _, X_df, _, _, _ = get_cached_matrices(year)

    return create_builder_historical_plot(shock, history, X_df, country_mapping, COLOR_PALETTE), base_style

@app.callback(
    [Output('builder-combined-chart', 'figure'),
     Output('builder-combined-chart', 'style')],
    [Input('scenario-store', 'data'),
     Input('year-dropdown', 'value')]
)
def update_builder_combined_chart(scenario_data, year):
    """Updates the historical chart for the combined scenario."""
    base_style = {'height': '300px'}
    if not scenario_data or len(scenario_data) < 2:
        return go.Figure(), {**base_style, 'display': 'none'}

    history = load_production_history()
    _, X_df, _, _, _ = get_cached_matrices(year)

    return create_builder_historical_plot(scenario_data, history, X_df, country_mapping, COLOR_PALETTE), base_style

@app.callback(
    Output("download-portfolio-yaml", "data"),
    Input("export-portfolio-button", "n_clicks"),
    State("portfolio-store", "data"),
    prevent_initial_call=True,
)
def export_portfolio(n_clicks, portfolio_data):
    """Exports the current portfolio to a YAML file."""
    if not portfolio_data:
        return dash.no_update

    yaml_string = yaml.dump(portfolio_data, default_flow_style=False, sort_keys=False)

    return dict(content=yaml_string, filename="vesdio_portfolio.yaml")

@app.callback(
    Output("download-yaml", "data"),
    Input("export-yaml-button", "n_clicks"),
    State("scenario-store", "data"),
    prevent_initial_call=True,
)
def export_scenario(n_clicks, scenario_data):
    """Exports the current scenario to a YAML file."""
    if not scenario_data:
        return dash.no_update

    yaml_string = yaml.dump(scenario_data, default_flow_style=False, sort_keys=False)

    return dict(content=yaml_string, filename="custom_shock_scenario.yaml")

@lru_cache(maxsize=None)
def get_cached_matrices(year):
    """Loads and caches all necessary matrices for a given year."""
    print(f"Cache miss: Loading matrices for year {year} from disk.")
    return load_mrio_matrices(year, matrices_to_load=['A', 'X', 'Y', 'L', 'G'])

@app.callback(
    [Output('impact-waterfall-chart', 'figure'),
     Output('country-impact-chart', 'figure'),
     Output('home-impact-barchart', 'figure'),
     Output('results-title', 'children'),
     Output('production-history-chart', 'figure'),
     Output('sankey-diagram', 'figure'),
     Output('top-impacts-table', 'children'),
     Output('portfolio-breakdown-content', 'children'),
     Output('results-output', 'style')],
    [Input('run-button', 'n_clicks')],
    [State('year-dropdown', 'value'),
     State('position-mode-toggle', 'value'),
     State('portfolio-store', 'data'),
     State('home-region-dropdown', 'value'),
     State('home-sector-dropdown', 'value'),
     State('shock-region-dropdown', 'value'), # Single mode region
     State('shock-sector-dropdown', 'value'), # Single mode sector
     State('scenario-store', 'data'),         # Builder mode data
     State('shock-magnitude-input', 'value'),
     State('model-method-toggle', 'value'),
     State('aggregation-toggle', 'value'),
     State('shock-type-toggle', 'value'),
     State('ecosystem-service-dropdown', 'value'),
     State('encore-data-store', 'data'),
     State('top-impacts-sort-toggle', 'value')]
)
def run_and_update_all_results(n_clicks, year, position_mode, portfolio_data, home_region, home_sector, shock_region, shock_sector, builder_shocks, magnitude, model_method, aggregation_level, shock_type, ecosystem_service, encore_data, top_impacts_sort_by):
    if n_clicks == 0:
        # Before the first run, hide the results panel and return empty figures/content
        empty_figs_and_content = [go.Figure()] * 3 + [""] + [go.Figure()] * 3 + [""]
        hidden_style = {'display': 'none'}
        return empty_figs_and_content + [hidden_style]

    # Determine shock mode based on whether the scenario store is populated
    shock_mode = 'builder' if builder_shocks else 'single'

    # This is the key change. If it's an ecosystem shock, we override the inputs
    # to look like a multi-shock scenario from the builder.
    if shock_mode == 'single' and shock_type == 'ecosystem':
        if encore_data and ecosystem_service:
            service_data = next((item for item in encore_data if item["service"] == ecosystem_service), None)
            if service_data:
                # `extract_sector_intensities` tolerates both the legacy
                # encore_materiality.json schema (a plain list of sector-name strings,
                # implying full dependency) and the enriched schema (a list of
                # {"sector", "intensity"} dicts) so this keeps working even if the
                # ingested data hasn't been regenerated with graded intensities yet.
                sector_intensities = extract_sector_intensities(service_data)

                # We need to get the list of countries for the selected region
                _, ALL_COUNTRIES, _, _ = load_labels_data(year)
                valid_region_groups = get_valid_region_groups(ALL_COUNTRIES)
                countries_to_shock = []
                if shock_region == 'All':
                    countries_to_shock = ALL_COUNTRIES
                elif shock_region in valid_region_groups:
                    countries_to_shock = valid_region_groups[shock_region]
                else:
                    countries_to_shock = [shock_region]

                # Create a list of shocks in the same format as the scenario builder,
                # but with each sector's magnitude differentiated by its ENCORE
                # dependency intensity (src/es_shock.py) rather than every material
                # sector receiving the same uniform `magnitude` (finding A2).
                current_builder_shocks = []
                for country in countries_to_shock:
                    for sector, intensity in sector_intensities.items():
                        current_builder_shocks.append({
                            'region': country,
                            'sector': sector,
                            'magnitude': effective_magnitude(magnitude, intensity),
                        })

                # Override shocks and mode
                builder_shocks = current_builder_shocks
                shock_mode = 'builder'
                shock_sector = None
                shock_region = None

    # This callback now acts as a high-level orchestrator.
    # It fetches cached data and passes all inputs to the handler function.
    cached_data = get_cached_matrices(year)
    return handle_simulation_results(
        n_clicks, year, position_mode, portfolio_data, home_region, home_sector,
        shock_mode, shock_region, shock_sector, builder_shocks, magnitude, model_method, aggregation_level, cached_data,
        country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE
    )

# --- New, purely-additive UI callbacks (WS1): persistent scenario-summary
# header and an explicit empty state before the first run. Neither touches
# any id/prop used by the callbacks above. --- #

@app.callback(
    Output('results-empty-state', 'style'),
    Input('run-button', 'n_clicks'),
)
def toggle_results_empty_state(n_clicks):
    """Shows an explicit empty state until the user has run the simulation once."""
    if not n_clicks:
        return {
            'textAlign': 'center',
            'padding': f"{SPACING[12]} {SPACING[4]}",
            'color': 'var(--color-text-muted)',
            'border': '1px dashed var(--color-border-strong)',
            'borderRadius': 'var(--radius-lg)',
        }
    return {'display': 'none'}

@app.callback(
    [Output('model-method-toggle', 'options'),
     Output('model-method-toggle', 'value')],
    [Input('year-dropdown', 'value'),
     Input('shock-type-toggle', 'value'),
     Input('shock-region-dropdown', 'value'),
     Input('shock-sector-dropdown', 'value'),
     Input('ecosystem-service-dropdown', 'value'),
     Input('shock-magnitude-input', 'value'),
     Input('scenario-store', 'data'),
     Input('encore-data-store', 'data')],
    State('model-method-toggle', 'value')
)
def update_constrained_lp_availability(year, shock_type, shock_region, shock_sector, ecosystem_service,
                                        magnitude, builder_shocks, encore_data, current_method):
    """Greys out the Constrained (LP) method whenever the currently-configured shock is
    predicted to need the analytical fallback (see `constrained_lp_would_fallback`), and
    silently switches away from it to Ghosh so the user can't select an option that
    won't actually run as the rigorous LP."""
    base_options = [
        {'label': 'Leontief (Demand-Side)', 'value': 'leontief'},
        {'label': 'Ghosh (Supply-Side)', 'value': 'ghosh'},
        {'label': 'Constrained (Rigorous LP, slower)', 'value': 'constrained'},
    ]

    shock_maps = builder_shocks or []
    if not shock_maps:
        if shock_type == 'ecosystem':
            if encore_data and ecosystem_service and shock_region and magnitude is not None:
                service_data = next((item for item in encore_data if item["service"] == ecosystem_service), None)
                if service_data:
                    sector_intensities = extract_sector_intensities(service_data)
                    _, ALL_COUNTRIES, _, _ = load_labels_data(year)
                    valid_region_groups = get_valid_region_groups(ALL_COUNTRIES)
                    if shock_region == 'All':
                        countries_to_shock = ALL_COUNTRIES
                    elif shock_region in valid_region_groups:
                        countries_to_shock = valid_region_groups[shock_region]
                    else:
                        countries_to_shock = [shock_region]
                    shock_maps = [
                        {'region': country, 'sector': sector, 'magnitude': effective_magnitude(magnitude, intensity)}
                        for country in countries_to_shock
                        for sector, intensity in sector_intensities.items()
                    ]
        elif shock_region and shock_sector and magnitude is not None:
            shock_maps = [{'region': shock_region, 'sector': shock_sector, 'magnitude': magnitude}]

    would_fallback = False
    if shock_maps:
        try:
            A_df, _, _, _, _ = get_cached_matrices(year)
            would_fallback = constrained_lp_would_fallback(A_df, shock_maps)
        except Exception:
            would_fallback = False

    options = [dict(opt) for opt in base_options]
    if would_fallback:
        options[2]['disabled'] = True

    new_value = 'ghosh' if (would_fallback and current_method == 'constrained') else dash.no_update
    return options, new_value


@app.callback(
    Output('scenario-summary-header', 'children'),
    [Input('position-mode-toggle', 'value'),
     Input('home-region-dropdown', 'value'),
     Input('home-sector-dropdown', 'value'),
     Input('shock-type-toggle', 'value'),
     Input('shock-region-dropdown', 'value'),
     Input('shock-sector-dropdown', 'value'),
     Input('ecosystem-service-dropdown', 'value'),
     Input('shock-magnitude-input', 'value'),
     Input('model-method-toggle', 'value'),
     Input('year-dropdown', 'value'),
     Input('scenario-store', 'data'),
     Input('portfolio-store', 'data')]
)
def update_scenario_summary_header(position_mode, home_region, home_sector, shock_type, shock_region, shock_sector,
                                    ecosystem_service, magnitude, model_method, year, scenario_data, portfolio_data):
    """Keeps a short, always-visible summary of the currently configured scenario
    in view, independent of whether results have been computed yet."""
    if position_mode == 'portfolio':
        position_text = f"Portfolio ({len(portfolio_data or [])} asset(s))"
    else:
        home_region_name = country_mapping.get(home_region, home_region) if home_region else "—"
        position_text = f"{home_sector or '—'} in {home_region_name}"

    if scenario_data:
        shock_text = f"Custom scenario ({len(scenario_data)} shock(s))"
    elif shock_type == 'ecosystem':
        shock_region_name = country_mapping.get(shock_region, shock_region) if shock_region else "—"
        shock_text = f"Ecosystem service shock: {ecosystem_service or '—'} in {shock_region_name}"
    else:
        shock_region_name = country_mapping.get(shock_region, shock_region) if shock_region else "—"
        shock_text = f"Sector shock: {shock_sector or '—'} in {shock_region_name}"

    method_label = "Ghosh (Supply-Side)" if model_method == 'ghosh' else "Leontief (Demand-Side)"

    return html.Div([
        dmc.Text([html.B("Position: "), position_text]),
        dmc.Text([html.B("Shock: "), shock_text]),
        dmc.Text([html.B("Magnitude: "), f"{magnitude}%  ·  ", html.B("Method: "), f"{method_label}  ·  ", html.B("Year: "), f"{year}"]),
    ])

if __name__ == '__main__':
    # Determine if running as a bundled executable
    is_frozen = getattr(sys, 'frozen', False)
    debug_mode = not is_frozen

    host = "127.0.0.1"
    port = 8050
    url = f"http://{host}:{port}"

    # --- First-run reference-data provisioning ---
    # The packaged executable no longer bundles the EXIOBASE dataset (see
    # vesdio.spec / docs/PACKAGING.md), so a frozen build needs to fetch it
    # from a GitHub Release before the app has anything real to show. This
    # must NEVER run in a normal dev/CI invocation of `python app.py` — the
    # dummy-data fallback (src/providers/exiobase._generate_dummy_data) is
    # what dev relies on, and it must keep working with no network at all.
    # `VESDIO_FETCH_DATA=1` is an explicit opt-in escape hatch for testing
    # the downloader locally without building an executable.
    if is_frozen or os.environ.get('VESDIO_FETCH_DATA'):
        from src.data_bootstrap import ensure_reference_data

        def _print_progress(value):
            # Keep this deliberately simple: a console progress line is
            # sufficient here (a pywebview splash window would need its own
            # server/HTML and isn't worth the complexity for a one-time,
            # short-lived download). `value` is either a float fraction in
            # [0, 1] or a short status string; render each accordingly.
            if isinstance(value, float):
                print(f"[data setup] {value * 100:.0f}%")
            else:
                print(f"[data setup] {value}")

        try:
            print("Checking for reference dataset (first run may download data)...")
            ok = ensure_reference_data(progress=_print_progress)
            if not ok:
                print(
                    "Could not fully provision reference data (no network, or the "
                    "release isn't published yet). VESDIO will start with the "
                    "synthetic dummy dataset instead."
                )
        except Exception as e:
            # Never let a downloader problem prevent the app from starting —
            # worst case, the per-loader dummy-data fallback kicks in.
            print(f"Reference data setup failed unexpectedly ({e}); continuing with dummy-data fallback.")

    try:
        # Desktop mode: run the Dash/Flask server on a background thread
        # bound to localhost, then host it inside a native pywebview
        # window instead of opening a browser tab. This is what makes
        # VESDIO behave like a real offline desktop app rather than a
        # web page the user has to keep a browser tab open for.
        import webview

        def run_server():
            # The reloader and debug mode are disabled here: the server
            # runs on a background thread, and Werkzeug's reloader forks
            # a second process, which does not play well with owning a
            # native window on the main thread.
            app.run(host=host, port=port, debug=False, use_reloader=False)

        server_thread = Thread(target=run_server, daemon=True)
        server_thread.start()

        print(f"Application ready. Opening native window pointed at {url}")
        webview.create_window("VESDIO", url, width=1400, height=900, min_size=(1024, 700))
        webview.start()
    except ImportError:
        # Fallback for any environment where pywebview isn't installed or
        # doesn't have a usable GUI backend (e.g. this dev/CI sandbox):
        # behave exactly as before and open a regular browser tab against
        # the Dash server.
        def open_browser():
            webbrowser.open_new(url)

        # For a bundled app, or when not in debug mode, open the browser directly.
        # For debug mode, only open it in the main Werkzeug process to avoid multiple tabs.
        if is_frozen or not os.environ.get("WERKZEUG_RUN_MAIN"):
            Timer(1, open_browser).start()

        print(f"pywebview not available; falling back to browser tab. Starting server on {url}")
        app.run(host=host, port=port, debug=debug_mode)

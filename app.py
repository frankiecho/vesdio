import dash
from dash import dcc, html
import dash.exceptions
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import numpy as np
from functools import lru_cache
import pandas as pd
import yaml
import base64
import io
import webbrowser
import os
from threading import Timer

# Import core functions from the src modules
from src.data_loader import load_labels_data, load_mrio_matrices, load_production_history, load_encore_materiality
from src.callbacks import handle_simulation_results
from src.config import country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE, get_valid_region_groups
from src.plotting import truncate_label, create_builder_historical_plot

# --- 1. Load Data and Pre-compute --- #
# Data will be loaded within the callback based on the selected year

# --- 2. Initialize Dash App --- #
app = dash.Dash(__name__,
    suppress_callback_exceptions=True,
    external_stylesheets=[{
        'href': 'https://codepen.io/chriddyp/pen/bWLwgP.css',
        'rel': 'stylesheet'
    }]
)
server = app.server

# --- 3. Define App Layout --- #
# Define dropdown styles
dropdown_style = {
    'lineHeight': '1.4',
    'maxHeight': '400px',
    'minHeight': '38px'
}

years = list(range(1995, 2022))

app.layout = html.Div(style={'fontFamily': 'Arial, sans-serif'}, children=[
    # Top Menu Bar
    html.Div(
        style={
            'backgroundColor': '#f0f0f0',
            'borderBottom': '1px solid #ddd',
            'padding': '10px 40px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between'
        },
        children=[
            html.H1("VESD.IO", style={'margin': 0, 'fontSize': '24px'}),
            html.Button("Instructions", id="open-instructions-button", n_clicks=0, className='button-primary')
        ]
    ),

    # Main Content Area
    html.Div(style={'padding': '20px'}, children=[
        # Left column for controls
        # This dcc.Store holds the list of shocks for the scenario builder
        dcc.Store(id='scenario-store', storage_type='memory', data=[]),
        dcc.Store(id='encore-data-store', storage_type='memory'),

        html.Div(className='four columns', style={'paddingRight': '20px'}, children=[
            # Run Button at the top
            html.Div(className='control-group', children=[
                html.Button('▶ Run Simulation', id='run-button', n_clicks=0, style={'fontSize': '18px', 'width': '100%', 'marginBottom': '20px'}),
            ]),

            # User Target Selection & Scenario Configuration
            html.Div(className='control-group', children=[
                html.H3("Your Position"),
                html.Label("Select Your Home Region:"),
                dcc.Dropdown(id='home-region-dropdown', style=dropdown_style),
                html.Label("Select Your Home Sector:", style={'marginTop': '10px'}),
                dcc.Dropdown(id='home-sector-dropdown', style=dropdown_style),
            ]),
            html.Div(className='control-group', style={'marginTop': '25px'}, children=[
                html.H3("Define Shock Event"),                
                html.Div(id='single-shock-controls', children=[
                    html.Label("Shocked Region:", style={'marginTop': '10px'}),
                    dcc.Dropdown(id='shock-region-dropdown', style=dropdown_style),
                    dcc.RadioItems(
                        id='shock-type-toggle',
                        options=[
                            {'label': 'Sector-Specific Shock', 'value': 'sector'},
                            {'label': 'Ecosystem Service Shock', 'value': 'ecosystem'},
                        ],
                        value='sector',
                        labelStyle={'display': 'inline-block', 'marginRight': '10px'}
                    ),
                    html.Div(id='sector-shock-controls', children=[
                        html.Label("Shocked Sector:", style={'marginTop': '10px'}),
                        dcc.Dropdown(id='shock-sector-dropdown', style=dropdown_style),
                    ]),
                    html.Div(id='ecosystem-shock-controls', style={'display': 'none'}, children=[
                        html.Label("Ecosystem Service:", style={'marginTop': '10px'}),
                        dcc.Dropdown(id='ecosystem-service-dropdown', style=dropdown_style),
                    ]),
                ]),
                html.Hr(),
                html.Button("Create Custom Scenario...", id='open-builder-button', n_clicks=0, style={'width': '100%'}),
                html.Div(id='builder-display-area', style={'display': 'none'}, children=[
                    html.Label("Custom Scenario Shocks:", style={'marginTop': '10px'}),
                    html.Div(id='main-scenario-display-list', style={'maxHeight': '150px', 'overflowY': 'auto', 'border': '1px solid #ccc', 'padding': '10px', 'backgroundColor': '#f9f9f9'}),
                    html.Div(className='row', style={'marginTop': '10px'}, children=[
                        html.Div(className='six columns', children=[
                            html.Button("Edit Scenario...", id='edit-builder-button', n_clicks=0, style={'width': '100%'})
                        ]),
                        html.Div(className='six columns', children=[
                            html.Button("Clear Scenario", id='clear-scenario-button', n_clicks=0, style={'width': '100%', 'backgroundColor': '#D55E00', 'color': 'white'})
                        ])
                    ])
                ]),
            ]),

            html.Div(className='control-group', style={'marginTop': '25px'}, children=[
                html.H3("Scenario Type & Magnitude"),
                html.Label("Select Year:"),
                dcc.Dropdown(
                    id='year-dropdown',
                    options=[{'label': str(y), 'value': y} for y in years],
                    value=2021,
                    style=dropdown_style
                ),
                html.Label("Calculation Method:", style={'marginTop': '10px'}),
                dcc.RadioItems(
                    id='model-method-toggle',
                    options=[
                        {'label': 'Leontief (Demand-Side)', 'value': 'leontief'},
                        {'label': 'Ghosh (Supply-Side)', 'value': 'ghosh'},
                    ],
                    value='ghosh',
                    labelStyle={'display': 'inline-block', 'marginRight': '10px'}
                ),
                html.Label("Scenario Type:", style={'marginTop': '10px'}),
                # Transition risk option removed as it's not ready
                html.P("Physical Risk (Supply Shock)", style={'padding': '5px', 'border': '1px solid #ccc', 'borderRadius': '5px', 'backgroundColor': '#f9f9f9'}),
                html.Label("Shock Magnitude (%):", style={'marginTop': '10px'}),
                dcc.Slider(
                    id='shock-magnitude-input',
                    min=0,
                    max=100,
                    step=1,
                    value=10,
                    marks={i: f'{i}%' for i in range(0, 101, 10)},
                    tooltip={"placement": "bottom", "always_visible": True}
                ),
            ])

            
        ]),

        # Right column for results
        html.Div(className='eight columns', style={'position': 'relative'}, children=[
            dcc.Loading(
                id="loading-results",
                type="default",
                # We'll achieve a custom translucent overlay using styles instead of fullscreen=True
                parent_style={
                    'position': 'absolute',
                    'top': 0,
                    'left': 0,
                    'width': '100%',
                    'height': '100%',
                    'zIndex': 999, # Ensure it's on top
                    'minHeight': '90vh'
                },
                children=html.Div(id='results-output', children=[
                    html.H3(id='results-title', style={'textAlign': 'center'}),
                    dcc.Tabs(id="results-tabs", children=[
                        dcc.Tab(label='Summary', children=[
                            html.Div(className='row', style={'marginTop': '20px'}, children=[
                                html.Div(className='six columns', children=[dcc.Graph(id='home-impact-barchart')]),
                                html.Div(className='six columns', children=[dcc.Graph(id='impact-waterfall-chart')]),
                            ]),
                            # Display Options
                            html.Div(className='control-group', style={'marginTop': '20px'}, children=[
                                html.H3("Display Options"),
                                html.Label("Aggregation Level:", style={'marginTop': '15px'}),
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
                            html.Div(style={'marginTop': '20px'}, children=[
                                dcc.Graph(id='country-impact-chart')
                            ])
                        ]),
                        dcc.Tab(label='Supply Chain Flow', children=[
                            html.Div(style={'marginTop': '20px'}, children=[
                                dcc.Graph(id='sankey-diagram')
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
                                    labelStyle={'display': 'inline-block', 'marginRight': '15px'}
                                ),
                            ], style={'padding': '15px'}),
                            html.Div(id='top-impacts-table'),
                        ]),
                        dcc.Tab(label='Historical Context', children=[
                            dcc.Graph(id='production-history-chart')
                        ]),
                    ])
                ])
            ),
        ]),
    ]),

    # Scenario Builder Modal
    html.Div(
        id="scenario-builder-modal",
        style={ # This is the main container for the modal
            'display': 'none', # Toggled by callback
            'position': 'fixed',
            'zIndex': 1001,
            'left': 0,
            'top': 0,
            'width': '100%',
            'height': '100%',
            'overflow': 'auto',
            'backgroundColor': 'rgba(0,0,0,0.4)' # The background overlay
        },
        children=[
            # This is the modal content box
            html.Div(style={'backgroundColor': '#fefefe', 'margin': '10% auto', 'padding': '20px', 'border': '1px solid #888', 'width': '80%', 'maxWidth': '800px'}, children=[
                # Header
                html.Div([
                    html.Span("×", id="modal-close-button", style={'color': '#aaa', 'float': 'right', 'fontSize': '28px', 'fontWeight': 'bold', 'cursor': 'pointer'}),
                    html.H2("Scenario Builder"),
                ]),
                # Body
                html.Div([
                    # --- Part 1: Add/Configure a single shock ---
                    html.H4("1. Configure a Shock"),
                    html.Div(className='row', children=[
                        html.Div(className='three columns', children=[
                            html.Label("Region:"),
                            dcc.Dropdown(id='builder-region-select')
                        ]),
                        html.Div(className='four columns', children=[
                            html.Label("Sector:"),
                            dcc.Dropdown(id='builder-sector-select')
                        ]),
                        html.Div(className='three columns', children=[
                            html.Label("Magnitude (%):"),
                            dcc.Slider(
                                id='builder-magnitude-input',
                                min=0, max=100, step=1, value=10,
                                marks={i: f'{i}%' for i in range(0, 101, 20)},
                                tooltip={"placement": "bottom", "always_visible": True}
                            )
                        ]),
                        html.Div(className='two columns', children=[
                            html.Button("Add Shock", id="builder-add-shock-button", n_clicks=0, style={'width': '100%', 'marginTop': '25px', 'padding': '5px', 'paddingTop': '0px'})
                        ]),
                    ]),
                    dcc.Loading(type="circle", children=dcc.Graph(id='builder-single-chart', style={'height': '300px'})),
                    html.Hr(),
                    # --- Part 2: Review the cumulative scenario ---
                    html.H4("2. Review Cumulative Scenario"),
                    html.Div(className='row', children=[
                        html.Div(className='six columns', children=[
                            html.H5("Current Shocks List"),
                            html.Div(id='scenario-display-list', style={'maxHeight': '250px', 'overflowY': 'auto', 'border': '1px solid #ccc', 'padding': '10px'})
                        ]),
                        html.Div(className='six columns', children=[
                            dcc.Loading(
                                type="circle", 
                                children=dcc.Graph(id='builder-combined-chart', style={'height': '300px'})
                            )
                        ])
                    ])
                ]),
                # Footer
                html.Div(className='row', style={'marginTop': '20px'}, children=[
                    html.Div(className='six columns', children=[
                        dcc.Upload(
                            id='upload-yaml',
                            children=html.Button('Import from YAML'),
                            multiple=False,
                            accept='.yaml,.yml'
                        )
                    ]),
                    html.Div(className='six columns', style={'textAlign': 'right'}, children=[
                        html.Button("Export to YAML", id="export-yaml-button", n_clicks=0),
                        dcc.Download(id="download-yaml"),
                        html.Button("Save and Close", id="modal-save-button", n_clicks=0, style={'marginLeft': '10px'})
                    ])
                ])
            ])
        ]
    ),

    # Instructions Modal
    html.Div(
        id="instructions-modal",
        style={ # Main container for the modal
            'display': 'none', # Toggled by callback
            'position': 'fixed', 'zIndex': 1002, 'left': 0, 'top': 0,
            'width': '100%', 'height': '100%', 'overflow': 'auto',
            'backgroundColor': 'rgba(0,0,0,0.4)'
        },
        children=[
            # Modal content box
            html.Div(style={'backgroundColor': '#fefefe', 'margin': '10% auto', 'padding': '20px', 'border': '1px solid #888', 'width': '80%', 'maxWidth': '700px'}, children=[
                # Header
                html.Div([
                    html.Span("×", id="instructions-modal-close-button", style={'color': '#aaa', 'float': 'right', 'fontSize': '28px', 'fontWeight': 'bold', 'cursor': 'pointer'}),
                    html.H2("How to Use VESD.IO"),
                ]),
                # Body with instructions
                dcc.Markdown('''
                    Welcome to the Valuing Ecosystem Service Dependencies with Input-Output (VESD.IO) tool. This application helps you simulate the economic impacts of ecosystem services and other supply chain disruption scenarios to your business.

                    #### **Step 1: Set Your Asset region and sector**
                    - **Home Region & Sector**: In the "Your Position" panel, select the country and industry sector that represents your organization's asset region and sector.

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
                    - The results will appear on the right. Use the tabs to explore different views:
                        - **Summary**: Key impacts on your home position and a waterfall chart showing contributing factors.
                        - **Geographic Impact**: A world map visualizing where these impacts come from in the world.
                        - **Supply Chain Flow**: A Sankey diagram showing how the impacts flow through the supply chain to affect your asset region and sector.
                        - **Global Impacts**: A table of the most affected sectors worldwide based on this supply chain disruption.
                        - **Historical Context**: A line chart showing the size of the impact on production relative to the production across historical time-periods.
                             
                    #### **Technical Note**
                    
                    The input-output models are based on EXIOBASE v3.9.6 (June 2025). It covers all 44 countries and 5 rest-of-world regions in EXIOBASE. 
                    
                    EXIOBASE citation: Stadler, K., Wood, R., Bulavskaya, T., Södersten, C.-J., Simas, M., Schmidt, S., Usubiaga, A., Acosta-Fernández, J., Kuenen, J., Bruckner, M., Giljum, S., Lutter, S., Merciai, S., Schmidt, J. H., Theurl, M. C., Plutzar, C., Kastner, T., Eisenmenger, N., Erb, K.-H., … Tukker, A. (2025). EXIOBASE 3 (3.9.6) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.15689391
                
                    The link between ecosystem services and sector production is calculated through materiality ratings in the ENCORE database. Sectors with "High" or "Very High" materiality to an ecosystem services are assumed to have production decreased in proportion to the specified magnitude of production disruption. Sectors without a "High" or "Very High" materiality rating to an ecosystem service is assumed to be unaffected.
                             
                    ENCORE citation: Global Canopy and UNEP (2025). Exploring Natural Capital Opportunities, Risk and Exposure (June 2025 update). https://encorenature.org/en
                ''')
            ])
        ]
    )
])

# --- 4. Define Callback Logic --- #

@app.callback(
    [Output('home-region-dropdown', 'options'),
     Output('home-sector-dropdown', 'options'),
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
    sector_options = [{'label': truncate_label(s), 'value': s} for s in SECTORS]

    # Add ecosystem services options for the dropdown
    encore_materiality = load_encore_materiality()
    ecosystem_services = sorted([item['service'] for item in encore_materiality])
    ecosystem_service_options = [{'label': s, 'value': s} for s in ecosystem_services]
    default_ecosystem_service = ecosystem_services[0] if ecosystem_services else None

    if DEFAULTS:
        default_home_region = DEFAULTS.get('home_region', COUNTRIES[0])
        default_home_sector = DEFAULTS.get('home_sector', SECTORS[0])
        default_shock_region = DEFAULTS.get('shock_region', COUNTRIES[1] if len(COUNTRIES) > 1 else COUNTRIES[0])
        default_shock_sector = DEFAULTS.get('shock_sector', SECTORS[1] if len(SECTORS) > 1 else SECTORS[0])
    else:
        default_home_region = COUNTRIES[0]
        default_home_sector = SECTORS[0]
        default_shock_region = COUNTRIES[1] if len(COUNTRIES) > 1 else COUNTRIES[0]
        default_shock_sector = SECTORS[1] if len(SECTORS) > 1 else SECTORS[0]

    return (country_options, sector_options, shock_country_options, country_options, 
            sector_options, sector_options, ecosystem_service_options, encore_materiality,
            default_home_region, default_home_sector, default_shock_region, 
            default_shock_sector, default_ecosystem_service)

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

@app.callback(
    Output('scenario-builder-modal', 'style'),
    [Input('open-builder-button', 'n_clicks'),
     Input('edit-builder-button', 'n_clicks'),
     Input('modal-save-button', 'n_clicks'),
     Input('modal-close-button', 'n_clicks')],
    [State('scenario-builder-modal', 'style')]
)
def toggle_modal(open_clicks, edit_clicks, save_clicks, close_clicks, current_style):
    ctx = dash.callback_context
    if not ctx.triggered:
        return current_style
    
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id in ['open-builder-button', 'edit-builder-button']:
        return {**current_style, 'display': 'block'}
    if trigger_id in ['modal-save-button', 'modal-close-button']:
        return {**current_style, 'display': 'none'}
    return current_style

@app.callback(
    Output('instructions-modal', 'style'),
    [Input('open-instructions-button', 'n_clicks'),
     Input('instructions-modal-close-button', 'n_clicks')],
    [State('instructions-modal', 'style')],
    prevent_initial_call=True
)
def toggle_instructions_modal(open_clicks, close_clicks, current_style):
    ctx = dash.callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if trigger_id == 'open-instructions-button':
        return {**current_style, 'display': 'block'}
    if trigger_id == 'instructions-modal-close-button':
        return {**current_style, 'display': 'none'}
    return current_style

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
            html.Button("×", id={'type': 'delete-shock-button', 'index': i}, n_clicks=0, style={'border': 'none', 'background': 'transparent', 'color': 'red', 'fontWeight': 'bold', 'cursor': 'pointer'})
        ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}))

    return current_shocks, display_items, display_items

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
     Output('results-output', 'style')],
    [Input('run-button', 'n_clicks')],
    [State('year-dropdown', 'value'),
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
def run_and_update_all_results(n_clicks, year, home_region, home_sector, shock_region, shock_sector, builder_shocks, magnitude, model_method, aggregation_level, shock_type, ecosystem_service, encore_data, top_impacts_sort_by):
    if n_clicks == 0:
        # Prevent the callback from firing on initial load
        raise dash.exceptions.PreventUpdate

    # Determine shock mode based on whether the scenario store is populated
    shock_mode = 'builder' if builder_shocks else 'single'

    # This is the key change. If it's an ecosystem shock, we override the inputs
    # to look like a multi-shock scenario from the builder.
    if shock_mode == 'single' and shock_type == 'ecosystem':
        if encore_data and ecosystem_service:
            service_data = next((item for item in encore_data if item["service"] == ecosystem_service), None)
            if service_data:
                dependent_sectors = service_data['sectors']
                
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

                # Create a list of shocks in the same format as the scenario builder
                current_builder_shocks = []
                for country in countries_to_shock:
                    for sector in dependent_sectors:
                        current_builder_shocks.append({'region': country, 'sector': sector, 'magnitude': magnitude})
                
                # Override shocks and mode
                builder_shocks = current_builder_shocks
                shock_mode = 'builder'
                shock_sector = None 
                shock_region = None

    # This callback now acts as a high-level orchestrator.
    # It fetches cached data and passes all inputs to the handler function.
    cached_data = get_cached_matrices(year)
    return handle_simulation_results(
        n_clicks, year, home_region, home_sector, shock_mode, shock_region, shock_sector, 
        builder_shocks, magnitude, model_method, aggregation_level, cached_data,
        country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE
    )

if __name__ == '__main__':
    host = "127.0.0.1"
    port = 8050
    url = f"http://{host}:{port}"

    def open_browser():
        webbrowser.open_new(url) 

    # The reloader will run this script twice. We only want to open the browser on the first run.
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        Timer(1, open_browser).start()
        
    print(f"Application ready. Starting server on {url}")
    app.run(host=host, port=port, debug=True)

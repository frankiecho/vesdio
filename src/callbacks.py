import dash
from dash import html
import plotly.graph_objects as go

from src.config import get_valid_region_groups
from src.data_loader import load_labels_data, load_production_history
from src.scenario_modeler import run_physical_risk, run_physical_risk_ghosh, attribute_output_change
from src.plotting import (
    create_historical_production_plot,
    create_before_after_barchart,
    create_waterfall_plot,
    create_choropleth_map,
    create_sankey_diagram,
    create_top_impacts_table
)

def handle_simulation_results(n_clicks, year, home_region, home_sector, shock_mode, shock_region, shock_sector, builder_shocks, magnitude, model_method, aggregation_level, cached_data, country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE):
    if n_clicks == 0:
        return [go.Figure()] * 7 + [{'display': 'none'}]
    
    A_df, X_df, Y_df, L_df, G_df = cached_data

    # --- Expand Shock Regions ---
    _, ALL_COUNTRIES, _, _ = load_labels_data(year)
    valid_region_groups = get_valid_region_groups(ALL_COUNTRIES)
    
    shock_maps = []
    if shock_mode == 'builder':
        # Scenario Builder: Use the list of custom shocks from the store
        if not builder_shocks:
            return [go.Figure()] * 3 + ["In Scenario Builder mode, please select at least one region and one sector."] + [go.Figure()] * 3 + [{'marginTop': '30px'}]
        
        for shock in builder_shocks:
            # The magnitude from the store is already 0-100, so convert it
            shock_maps.append({
                'region': shock['region'], 
                'sector': shock['sector'], 
                'magnitude': shock['magnitude'] / 100.0
            })
    else:
        # Single Shock Mode
        magnitude_prop = magnitude / 100.0
        countries_to_shock = []
        if shock_region == 'All':
            countries_to_shock = ALL_COUNTRIES
        elif shock_region in valid_region_groups:
            countries_to_shock = valid_region_groups[shock_region]
        else: # It's a single country
            countries_to_shock = [shock_region]

        for country in countries_to_shock:
            shock_maps.append({'region': country, 'sector': shock_sector, 'magnitude': magnitude_prop})

    # Run selected model
    if model_method == 'ghosh':
        _, delta_x = run_physical_risk_ghosh(A_df, X_df, G_df, shock_maps)
    else: # Leontief
        _, delta_x = run_physical_risk(A_df, X_df, Y_df, L_df, shock_maps)

    if delta_x is None:
        return [go.Figure()] * 3 + ["Model run failed."] + [go.Figure()] * 3 + [{'marginTop': '30px'}]

    # --- Generate Plots ---
    production_history = load_production_history()
    history_fig = create_historical_production_plot(production_history, X_df, shock_maps, country_mapping, COLOR_PALETTE)
    
    home_impact_fig = create_before_after_barchart(X_df, delta_x, home_region, home_sector, country_mapping, COLOR_PALETTE)
    
    # Perform attribution analysis for all models
    attribution_dict = attribute_output_change(model_method, delta_x, shock_maps, home_region, home_sector, L_df, G_df, A_df)
    waterfall_fig = create_waterfall_plot(attribution_dict, aggregation_level, country_mapping, COLOR_PALETTE)
    country_fig = create_choropleth_map(attribution_dict, country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE)
    
    sankey_fig = create_sankey_diagram(A_df, delta_x, shock_maps, home_region, home_sector, country_mapping, COLOR_PALETTE)

    top_impacts_table = create_top_impacts_table(delta_x, X_df, shock_maps, country_mapping, COLOR_PALETTE)

    # --- Create Title ---
    home_label = (home_region, home_sector)
    before_shock_output = X_df.loc[home_label, 'GrossOutput']
    delta_x_home = delta_x.loc[home_label]
    percentage_change = (delta_x_home / before_shock_output) * 100 if before_shock_output > 1e-9 else 0.0

    home_region_name = country_mapping.get(home_region, home_region)
    
    if shock_mode == 'builder':
        title_text = f"A custom scenario with {len(shock_maps)} shock(s)..."
    else:
        # This block now handles the case where shock_region might be None (e.g., for ecosystem shocks)
        shock_region_name = "N/A"
        if shock_region:
            shock_region_name = country_mapping.get(shock_region, shock_region) if shock_region != 'All' else 'All Regions'
        if shock_region in valid_region_groups: shock_region_name = shock_region # Use group name
        if shock_sector:
            title_text = f"A {magnitude}% shock to '{shock_sector}' in {shock_region_name}..."
        else: # This handles the ecosystem service case where shock_sector is None
            title_text = f"An ecosystem service shock affecting {len(shock_maps)} sector(s)..."

    subtitle_text = f"...causes a {percentage_change:,.2f}% change in output for '{home_sector}' in {home_region_name}."
    title = html.Div([
        html.H3(title_text, style={'textAlign': 'center', 'marginBottom': '5px'}),
        html.H4(subtitle_text, style={'textAlign': 'center', 'marginTop': '0px', 'color': COLOR_PALETTE['red'] if percentage_change < 0 else COLOR_PALETTE['green']})
    ])

    return waterfall_fig, country_fig, home_impact_fig, title, history_fig, sankey_fig, top_impacts_table, {'marginTop': '30px'}
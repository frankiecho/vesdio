import plotly.graph_objects as go
import pandas as pd
import numpy as np
from dash import dash_table, html

def truncate_label(label, max_length=60):
    """Shortens a string to a max length and adds '...' if truncated."""
    if len(label) > max_length:
        return label[:max_length - 3] + '...'
    return label

def create_historical_production_plot(production_history, X_df, shock_maps, country_mapping, COLOR_PALETTE):
    """Generates the historical production plot with the post-shock level."""
    fig = go.Figure()
    if production_history is None or not shock_maps:
        fig.update_layout(title_text="Historical production data not available or no shock defined.")
        return fig

    try:
        shock_labels = [(s['region'], s['sector']) for s in shock_maps]
        
        # Sum historical production across all selected shocks
        # We need to handle cases where a region is 'World' which is not in the history index
        valid_labels = [label for label in shock_labels if label in production_history.index]
        historical_series = production_history.loc[valid_labels].sum(axis=0).dropna()
        
        # Calculate pre- and post-shock totals
        base_output_total = 0
        post_shock_output_total = 0

        for shock in shock_maps:
            label = (shock['region'], shock['sector'])
            magnitude_prop = shock['magnitude']
            base_output = X_df.loc[label, 'GrossOutput']
            
            base_output_total += base_output
            post_shock_output_total += base_output * (1 - magnitude_prop)

        if historical_series.empty:
            raise KeyError

        fig.add_trace(go.Scatter(
            x=historical_series.index, y=historical_series.values, mode='lines+markers',
            name='Historical Production', line=dict(color=COLOR_PALETTE['blue'])
        ))
        fig.add_hline(y=post_shock_output_total, line_width=3, line_dash="dash", line_color=COLOR_PALETTE['red'],
                      annotation_text="Post-Shock Output", annotation_position="bottom right")

        if len(shock_maps) == 1:
            s = shock_maps[0]
            region_name = country_mapping.get(s['region'], s['region'])
            title = f"Historical Production for '{s['sector']}' in {region_name}"
        else:
            title = f"Combined Historical Production for {len(shock_maps)} Affected Sectors"

        fig.update_layout(
            title_text=title,
            xaxis_title="Year", yaxis_title="Gross Output (Monetary Units)",
            yaxis_range=[0, max(historical_series.max(), post_shock_output_total) * 1.1],
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showline=True, linecolor='black', linewidth=1),
            yaxis=dict(showline=True, linecolor='black', linewidth=1),
            showlegend=False
        )
    except KeyError:
        fig.update_layout(title_text=f"No historical data for the selected shock scenario.")

    return fig

def create_before_after_barchart(X_df, delta_x, home_region, home_sector, country_mapping, COLOR_PALETTE, is_portfolio=False, portfolio_before=0, portfolio_after=0):
    """Generates the before/after impact bar chart for the home sector."""
    fig = go.Figure()

    if is_portfolio:
        before_shock_output = portfolio_before
        after_shock_output = portfolio_after
        title_text = "Impact on Total Portfolio Value"
    else:
        home_label = (home_region, home_sector)
        before_shock_output = X_df.loc[home_label, 'GrossOutput']
        after_shock_output = before_shock_output + delta_x.loc[home_label]
        title_text = f"Impact on Gross Output for '{home_sector}' in {country_mapping.get(home_region, home_region)}"

    fig.add_trace(go.Bar(
        x=['Before Shock', 'After Shock'],
        y=[before_shock_output, after_shock_output],
        text=[f"{before_shock_output:,.0f}", f"{after_shock_output:,.0f}"],
        textposition='auto',
        marker_color=[COLOR_PALETTE['blue'], COLOR_PALETTE['red']]
    ))
    fig.update_layout(
        title_text=title_text,
        yaxis_title="Gross Output (Monetary Units)",
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showline=True, linecolor='black', linewidth=1),
        yaxis=dict(showline=True, linecolor='black', linewidth=1),
        showlegend=False
    )
    fig.update_yaxes(rangemode="tozero")
    return fig

def create_waterfall_plot(attribution_dict, aggregation_level, country_mapping, COLOR_PALETTE):
    """Generates the waterfall plot showing impact contributors."""
    if not attribution_dict.get('causes'):
        return go.Figure().update_layout(title=attribution_dict.get('message', 'No impact to display'))

    # Aggregate data based on user selection
    if aggregation_level == 'country':
        totals = {}
        for label, value in attribution_dict['causes'].items():
            region = label.split(" - ", 1)[0]
            totals[country_mapping.get(region, region)] = totals.get(country_mapping.get(region, region), 0) + value
    elif aggregation_level == 'sector':
        totals = {}
        for label, value in attribution_dict['causes'].items():
            sector = label.split(" - ", 1)[1]
            totals[sector] = totals.get(sector, 0) + value
    else: # 'none'
        totals = {f"{country_mapping.get(label.split(' - ')[0], label.split(' - ')[0])} - {label.split(' - ')[1]}": value 
                  for label, value in attribution_dict['causes'].items()}

    all_items = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    
    top_items = all_items[:3]
    labels = [label for label, _ in top_items]
    values = [value for _, value in top_items]
    
    remaining_sum = sum(value for _, value in all_items[3:])
    if remaining_sum > 1e-6:
        labels.append("Others")
        values.append(remaining_sum)

    # Add total
    total_value = sum(values)
    labels.append('Total')
    values.append(total_value)
    
    measures = ['relative'] * (len(values) - 1) + ['total']
    
    fig = go.Figure(go.Waterfall(
        name="Top Contributors", orientation="v", measure=measures, x=labels, y=values,
        text=[f"{val:.1f}%" for val in values], textposition="outside",
        connector={"line": {"color": "rgb(63, 63, 63)"}}
    ))
    
    top_3_percentage = sum(v for _, v in top_items)
    fig.update_layout(
        title={
            'text': f"Top Contributors to Output Change<br><sub>(Top 3 account for {top_3_percentage:.1f}% of total impact)</sub>",
            'y':0.95, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'
        },
        showlegend=False, yaxis_title="Contribution to Output Change (%)",
        margin=dict(t=100), yaxis_range=[0, max(110, total_value * 1.1)],
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showline=True, linecolor='black', linewidth=1),
        yaxis=dict(showline=True, linecolor='black', linewidth=1)
    )
    return fig

def create_choropleth_map(attribution_dict, country_mapping, COUNTRY_CODES_3_LETTER, COLOR_PALETTE):
    """Generates the choropleth map of country contributions."""
    if not attribution_dict.get('causes'):
        return go.Figure().update_layout(title=attribution_dict.get('message', 'No geographic impact to display'))

    country_totals = {}
    for label, value in attribution_dict['causes'].items():
        region = label.split(" - ", 1)[0]
        country_totals[region] = country_totals.get(region, 0) + value
    
    country_attribution = pd.Series(country_totals)
    country_codes = country_attribution.index.map(COUNTRY_CODES_3_LETTER.get)
    valid_indices = country_codes.notna()
    
    hover_text = [f"{country_mapping.get(country, country)}<br>Contribution: {value:.1f}%"
                  for country, value in zip(country_attribution.index[valid_indices], country_attribution.values[valid_indices])]

    fig = go.Figure(go.Choropleth(
        locations=country_codes[valid_indices], z=country_attribution.values[valid_indices],
        text=hover_text, hoverinfo='text',
        colorscale=[[0, COLOR_PALETTE['beige']], [0.5, COLOR_PALETTE['amber']], [1, COLOR_PALETTE['red']]],
        reversescale=False, marker_line_color='darkgray', marker_line_width=0.5,
        colorbar_title="Contribution (%)"
    ))
    fig.update_layout(
        title={'text': 'Geographic Source of Impact', 'y':0.95, 'x':0.5, 'xanchor': 'center', 'yanchor': 'top'},
        geo=dict(
            showframe=False, showcoastlines=True, coastlinecolor="Gray",
            showland=True, landcolor="LightGray", showocean=True, oceancolor="Azure",
            projection_type='equirectangular'
        ),
        margin=dict(t=40, b=0), paper_bgcolor='rgba(0,0,0,0)'
    )
    return fig

def create_sankey_diagram(A_df, delta_x, shock_maps, home_region, home_sector, country_mapping, COLOR_PALETTE, max_intermediaries=5):
    """
    Generates a Sankey diagram showing the flow of impact from shocked sectors
    to the home sector through the most significant intermediate sectors.
    """
    shock_labels = [(s['region'], s['sector']) for s in shock_maps]
    home_label = (home_region, home_sector)
    
    input_reduction_flows = A_df.multiply(delta_x, axis='columns').abs()

    suppliers_to_home = input_reduction_flows.loc[:, home_label].nlargest(max_intermediaries * 3).index
    customers_of_shock = input_reduction_flows.loc[shock_labels, :].sum(axis=0).nlargest(max_intermediaries * 3).index

    top_intermediaries = suppliers_to_home.intersection(customers_of_shock)
    top_intermediaries = top_intermediaries.drop(shock_labels, errors='ignore').drop(home_label, errors='ignore')
    top_intermediaries = top_intermediaries[:max_intermediaries]

    sources, targets, values = [], [], []
    
    all_nodes = sorted(list(set(shock_labels + top_intermediaries.tolist() + [home_label])), key=str)
    node_map = {node: i for i, node in enumerate(all_nodes)}
    node_labels = [f"{country_mapping.get(r, r)} - {s}" for r, s in all_nodes]

    # Assign colors to nodes based on their role
    node_colors = []
    for node in all_nodes:
        if node in shock_labels:
            node_colors.append(COLOR_PALETTE['red'])
        elif node == home_label:
            node_colors.append(COLOR_PALETTE['blue'])
        else:
            node_colors.append(COLOR_PALETTE['amber'])

    # 1. Shock -> Intermediary
    for s_node in shock_labels:
        for i_node in top_intermediaries:
            flow = input_reduction_flows.loc[s_node, i_node]
            if flow > 1e-6:
                sources.append(node_map[s_node])
                targets.append(node_map[i_node])
                values.append(flow)

    # 2. Intermediary -> Home
    for i_node in top_intermediaries:
        flow = input_reduction_flows.loc[i_node, home_label]
        if flow > 1e-6:
            sources.append(node_map[i_node])
            targets.append(node_map[home_label])
            values.append(flow)

    # 3. Direct Shock -> Home
    for s_node in shock_labels:
        flow = input_reduction_flows.loc[s_node, home_label]
        if flow > 1e-6:
            sources.append(node_map[s_node])
            targets.append(node_map[home_label])
            values.append(flow)

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15, thickness=20, line=dict(color="black", width=0.5), 
            label=node_labels,
            color=node_colors
        ),
        link=dict(
            source=sources, target=targets, value=values, color="rgba(153, 153, 153, 0.4)" # Corresponds to #999999 (grey) with alpha
        )
    )])
    
    title = "Supply Chain Impact Flow"
    if not sources:
        fig.add_annotation(text="No significant intermediary links found.", showarrow=False)

    fig.update_layout(title_text=title, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def create_portfolio_sankey_diagram(A_df, delta_x, shock_maps, portfolio_data, country_mapping, COLOR_PALETTE, max_intermediaries=5):
    """
    Generates an aggregated Sankey diagram for a portfolio, showing the flow of impact
    from shocked sectors to the total portfolio through key intermediaries.
    """
    shock_labels = [(s['region'], s['sector']) for s in shock_maps]
    portfolio_labels = [(p['region'], p['sector']) for p in portfolio_data]
    portfolio_weights = {(p['region'], p['sector']): p['weight'] / 100.0 for p in portfolio_data}

    # Calculate the monetary value of reduced input flows between all sectors
    input_reduction_flows = A_df.multiply(delta_x, axis='columns').abs()

    # Find top intermediaries: sectors that are both major customers of the shock
    # and major suppliers to the portfolio.
    customers_of_shock = input_reduction_flows.loc[shock_labels, :].sum(axis=0).nlargest(max_intermediaries * 3).index
    
    # Weighted sum of flows to portfolio assets
    suppliers_to_portfolio = pd.Series(0.0, index=A_df.index)
    for p_label, weight in portfolio_weights.items():
        suppliers_to_portfolio += input_reduction_flows.loc[:, p_label] * weight
    
    top_suppliers_to_portfolio = suppliers_to_portfolio.nlargest(max_intermediaries * 3).index

    top_intermediaries = customers_of_shock.intersection(top_suppliers_to_portfolio)
    top_intermediaries = top_intermediaries.drop(shock_labels, errors='ignore').drop(portfolio_labels, errors='ignore')
    top_intermediaries = top_intermediaries[:max_intermediaries]

    # --- Build Sankey Data ---
    sources, targets, values = [], [], []
    
    # Define nodes: Shocks, Intermediaries, and a single "Total Portfolio" node
    portfolio_node_label = "Total Portfolio"
    all_nodes_tuples = sorted(list(set(shock_labels + top_intermediaries.tolist())), key=str)
    
    node_labels = [f"{country_mapping.get(r, r)} - {s}" for r, s in all_nodes_tuples] + [portfolio_node_label]
    node_map = {node: i for i, node in enumerate(all_nodes_tuples)}
    portfolio_node_index = len(node_labels) - 1

    # Assign colors
    node_colors = [COLOR_PALETTE['red']] * len(shock_labels) + \
                  [COLOR_PALETTE['amber']] * len(top_intermediaries) + \
                  [COLOR_PALETTE['blue']]

    # 1. Shock -> Intermediary flows
    for s_node in shock_labels:
        for i_node in top_intermediaries:
            flow = input_reduction_flows.loc[s_node, i_node]
            if flow > 1e-6:
                sources.append(node_map[s_node])
                targets.append(node_map[i_node])
                values.append(flow)

    # 2. Intermediary -> Portfolio flows (weighted sum)
    for i_node in top_intermediaries:
        total_flow_to_portfolio = suppliers_to_portfolio.get(i_node, 0)
        if total_flow_to_portfolio > 1e-6:
            sources.append(node_map[i_node])
            targets.append(portfolio_node_index)
            values.append(total_flow_to_portfolio)

    # 3. Direct Shock -> Portfolio flows (weighted sum)
    for s_node in shock_labels:
        direct_flow_to_portfolio = sum(input_reduction_flows.loc[s_node, p_label] * weight for p_label, weight in portfolio_weights.items())
        if direct_flow_to_portfolio > 1e-6:
            sources.append(node_map[s_node])
            targets.append(portfolio_node_index)
            values.append(direct_flow_to_portfolio)

    fig = go.Figure(data=[go.Sankey(
        node=dict(pad=15, thickness=20, line=dict(color="black", width=0.5), label=node_labels, color=node_colors),
        link=dict(source=sources, target=targets, value=values, color="rgba(153, 153, 153, 0.4)")
    )])
    
    title = "Aggregated Supply Chain Impact Flow to Portfolio"
    if not sources:
        fig.add_annotation(text="No significant intermediary links found for the portfolio.", showarrow=False)

    fig.update_layout(title_text=title, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

def create_portfolio_breakdown_display(portfolio_data, delta_x, X_df, country_mapping, COLOR_PALETTE):
    """
    Creates a table and summary for the portfolio breakdown tab.
    """
    records = []
    total_before = 0
    total_after = 0

    for item in portfolio_data:
        label = (item['region'], item['sector'])
        weight = item['weight']
        
        before_val = X_df.loc[label, 'GrossOutput']
        delta_val = delta_x.loc[label]
        after_val = before_val + delta_val
        
        relative_change = (delta_val / before_val) * 100 if before_val > 1e-9 else 0

        records.append({
            'Region': country_mapping.get(item['region'], item['region']),
            'Sector': item['sector'],
            'Weight (%)': weight,
            'Absolute Change': delta_val,
            'Relative Change (%)': relative_change
        })
        
        # For weighted total calculation
        weight_prop = weight / 100.0
        total_before += before_val * weight_prop
        total_after += after_val * weight_prop

    # Create DataFrame for the table
    df = pd.DataFrame(records)

    # Create the DataTable
    table = dash_table.DataTable(
        columns=[
            {"name": "Region", "id": "Region"},
            {"name": "Sector", "id": "Sector"},
            {"name": "Weight (%)", "id": "Weight (%)", "type": "numeric", "format": dash_table.Format.Format(precision=1, scheme=dash_table.Format.Scheme.fixed)},
            {"name": "Absolute Change", "id": "Absolute Change", "type": "numeric", "format": dash_table.Format.Format(group=",", precision=0, scheme=dash_table.Format.Scheme.fixed)},
            {"name": "Relative Change (%)", "id": "Relative Change (%)", "type": "numeric", "format": dash_table.Format.Format(precision=2, scheme=dash_table.Format.Scheme.fixed, symbol=dash_table.Format.Symbol.yes, symbol_suffix='%').sign(dash_table.Format.Sign.positive)},
        ],
        data=df.to_dict('records'),
        sort_action="native",
        style_table={'overflowX': 'auto'},
        style_header={'backgroundColor': COLOR_PALETTE['grey'], 'color': 'white', 'fontWeight': 'bold'},
        style_cell={'textAlign': 'left', 'padding': '5px', 'whiteSpace': 'normal', 'height': 'auto', 'fontFamily': 'Arial, sans-serif', 'textAlign': 'left', 'padding': '5px', 'whiteSpace': 'normal', 'height': 'auto'},
        style_data_conditional=[
            {'if': {'column_id': 'Absolute Change', 'filter_query': '{Absolute Change} < 0'}, 'color': COLOR_PALETTE['red']},
            {'if': {'column_id': 'Relative Change (%)', 'filter_query': '{Relative Change (%)} < 0'}, 'color': COLOR_PALETTE['red']}
        ]
    )

    # Create the summary footer
    total_abs_change = total_after - total_before
    total_rel_change = (total_abs_change / total_before) * 100 if total_before > 1e-9 else 0

    summary_style = {'fontSize': '1.2em', 'fontWeight': 'bold', 'padding': '10px', 'borderTop': '2px solid black', 'marginTop': '20px'}
    summary = html.Div([
        html.H4("Total Portfolio Impact"),
        html.Table([
            html.Tr([
                html.Td("Total Absolute Change:", style={'paddingRight': '20px'}),
                html.Td(f"{total_abs_change:,.0f}", style={'color': COLOR_PALETTE['red'] if total_abs_change < 0 else COLOR_PALETTE['green']})
            ]),
            html.Tr([
                html.Td("Total Relative Change:", style={'paddingRight': '20px'}),
                html.Td(f"{total_rel_change:.2f}%", style={'color': COLOR_PALETTE['red'] if total_rel_change < 0 else COLOR_PALETTE['green']})
            ])
        ])
    ], style=summary_style)

    return html.Div([
        html.H3("Individual Asset Impacts"),
        table,
        summary
    ])

def create_top_impacts_table(delta_x, X_df, shock_maps, country_mapping, COLOR_PALETTE):
    """
    Creates a DataTable showing the top 100 most impacted sectors globally.
    Excludes the sectors that were directly shocked.
    """
    shock_labels = [(s['region'], s['sector']) for s in shock_maps]

    percentage_change = (delta_x / X_df['GrossOutput']).replace([np.inf, -np.inf], 0).fillna(0) * 100
    
    impact_df = pd.DataFrame({
        'Country': delta_x.index.get_level_values('region').map(country_mapping),
        'Sector': delta_x.index.get_level_values('sector'),
        'Output Change (Monetary)': delta_x,
        'Output Change (%)': percentage_change
    })
    
    impact_df.drop(index=shock_labels, inplace=True, errors='ignore')

    # Sort by absolute percentage change to get the top 100
    top_100_impacted = impact_df.reindex(impact_df['Output Change (%)'].abs().sort_values(ascending=False).index).head(100)

    columns = [
        {"name": "Country", "id": "Country"},
        {"name": "Sector", "id": "Sector"},
        {"name": "Output Change (Monetary)", "id": "Output Change (Monetary)", "type": "numeric", "format": dash_table.Format.Format(group=",", precision=0, scheme=dash_table.Format.Scheme.fixed)},
        {"name": "Output Change (%)", "id": "Output Change (%)", "type": "numeric", "format": dash_table.Format.Format(precision=2, scheme=dash_table.Format.Scheme.fixed, symbol=dash_table.Format.Symbol.yes, symbol_suffix='%').sign(dash_table.Format.Sign.positive)},
    ]

    data = top_100_impacted.to_dict('records')

    return dash_table.DataTable(
        id='global-impacts-datatable',
        columns=columns,
        data=data,
        sort_action="native",
        sort_mode="multi",
        page_size=20,
        style_table={'height': '600px', 'overflowY': 'auto'},
        style_header={
            'backgroundColor': COLOR_PALETTE['grey'],
            'color': 'white',
            'fontWeight': 'bold'
        },
        style_cell={
            'fontFamily': 'Arial, sans-serif',
            'textAlign': 'left',
            'padding': '5px',
            'whiteSpace': 'normal',
            'height': 'auto',
        },
        style_data_conditional=[
            {
                'if': {'column_id': 'Output Change (%)', 'filter_query': '{Output Change (%)} < 0'},
                'color': COLOR_PALETTE['red']
            },
            {
                'if': {'column_id': 'Output Change (Monetary)', 'filter_query': '{Output Change (Monetary)} < 0'},
                'color': COLOR_PALETTE['red']
            }
        ]
    )

def create_builder_historical_plot(shocks, production_history, X_df, country_mapping, COLOR_PALETTE):
    """
    Generates a historical production plot for the scenario builder.
    Can plot a single shock or the combined total of multiple shocks.
    """
    fig = go.Figure()
    if not shocks or production_history is None or X_df is None:
        return fig.update_layout(title_text="Select a shock to see historical context.")

    try:
        shock_labels = [(s['region'], s['sector']) for s in shocks]
        
        # Sum historical production across all selected shocks
        historical_series = production_history.loc[shock_labels].sum(axis=0).dropna()
        
        # Calculate pre- and post-shock totals
        base_output_total = 0
        post_shock_output_total = 0

        for shock in shocks:
            label = (shock['region'], shock['sector'])
            magnitude_prop = shock['magnitude'] / 100.0
            base_output = X_df.loc[label, 'GrossOutput']
            
            base_output_total += base_output
            post_shock_output_total += base_output * (1 - magnitude_prop)

        if historical_series.empty:
            raise KeyError

        fig.add_trace(go.Scatter(
            x=historical_series.index, y=historical_series.values, mode='lines+markers',
            name='Historical Production', line=dict(color=COLOR_PALETTE['blue'])
        ))
        fig.add_hline(y=post_shock_output_total, line_width=3, line_dash="dash", line_color=COLOR_PALETTE['red'],
                      annotation_text="Post-Shock Output", annotation_position="bottom right")

        if len(shocks) == 1:
            s = shocks[0]
            region_name = country_mapping.get(s['region'], s['region'])
            title = f"Historical Production for '{s['sector']}' in {region_name}"
        else:
            title = f"Combined Historical Production for {len(shocks)} Shocks"

        fig.update_layout(
            title_text=title,
            xaxis_title="Year", yaxis_title="Gross Output",
            yaxis_range=[0, max(historical_series.max(), post_shock_output_total) * 1.1],
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(showline=True, linecolor='black', linewidth=1),
            yaxis=dict(showline=True, linecolor='black', linewidth=1),
            showlegend=False,
            margin=dict(t=40, b=20, l=20, r=20)
        )
    except (KeyError, AttributeError):
        fig.update_layout(title_text="No historical data available for the selection.")

    return fig
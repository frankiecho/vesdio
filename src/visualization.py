
import plotly.graph_objects as go

def plot_waterfall_impact(attribution_df):
    """
    Creates a waterfall chart to visualize the sources of impact.

    Args:
        attribution_df (pd.Series): A series of impacts attributed to different sources.

    Returns:
        go.Figure: A Plotly waterfall chart figure.
    """
    # The model calculates losses as negative values. For a waterfall, it's more intuitive
    # to show these as positive contributions to the total loss.
    plot_data = -attribution_df[attribution_df != 0]

    if plot_data.empty:
        return go.Figure().update_layout(
            title="No significant impact to display.",
            xaxis_visible=False,
            yaxis_visible=False
        )

    fig = go.Figure(go.Waterfall(
        name="Impact Attribution",
        orientation="v",
        measure=["relative"] * len(plot_data) + ["total"],
        x=list(plot_data.index) + ["Total Impact"],
        y=list(plot_data.values) + [plot_data.sum()],
        text=[f"{v:,.2f}" for v in plot_data.values] + [f"{plot_data.sum():,.2f}"],
        textposition="outside",
        connector={"line": {"color": "rgb(63, 63, 63)"}},
    ))

    fig.update_layout(
        title="Attribution of Impact to Your Sector (Monetary Loss)",
        showlegend=True,
        yaxis_title="Monetary Value",
        xaxis_title="Shock Propagation Order"
    )
    
    return fig

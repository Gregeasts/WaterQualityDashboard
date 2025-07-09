import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, callback,no_update,State,dash_table,html,ctx
from dash.dependencies import State, ALL, MATCH
from flask import Flask
import calendar
import plotly.graph_objects as go
from statsmodels.nonparametric.smoothers_lowess import lowess
from collections import Counter
import numpy as np
import datetime
import os
print(f"PID: {os.getpid()}")
cols = [
    'Orthophosphate, reactive as P (mg/l)', 'Temperature of Water (°C)',
    'Ammoniacal Nitrogen as N (mg/l)', 'Phosphorus, Total as P (mg/l)',
    'Nitrogen, Total Oxidised as N (mg/l)', 'Nitrate as N (mg/l)',
    'Nitrite as N (mg/l)', 'Nitrogen, Total as N (mg/l)',
    'Alkalinity to pH 4.5 as CaCO3 (mg/l)', 'pH (phunits)',
    'Oxygen, Dissolved, % Saturation (%)', 'Oxygen, Dissolved as O2 (mg/l)',
    'BOD : 5 Day ATU (mg/l)', 'Solids, Suspended at 105 C (mg/l)'
]


# Load data
df = pd.read_parquet("mappable.parquet")
# Split comma-separated test types and get unique trimmed entries
# Flatten and split test types
split_test_types = df['Test_Type'].dropna().str.lower().str.split(',').explode()
split_test_types = split_test_types.str.strip()

# Count and sort by frequency
type_counts = Counter(split_test_types)
test_types_x = [t for t, _ in type_counts.most_common()]


# Aggregate location info
location_info = df.groupby("Location_ID").agg({
    "Location_Name": "first",
    "Longitude": "first",
    "Latitude": "first",
    "Sample_Count":"first",
    "Test_Type": lambda x: ", ".join(sorted(set(x.dropna())))
}).reset_index()

# Flask server
server = Flask(__name__)

# Dash app inside Flask
app = Dash(__name__, server=server, url_base_pathname="/", suppress_callback_exceptions=True)

# Layout
app.index_string = open("templates/index.html", "r").read()


app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='scroll-store'),
    dcc.Store(id='store-mode'),
    dcc.Store(id='store-test-type'),
    dcc.Store(id='store-parameter'),
    dcc.Store(id='store-slider'),
    dcc.Store(id='selected-locations-store', data=[]),

    html.H2("South West Water Quality Dashboard", style={"textAlign": "center"}),

    html.Div(id='main-content'),

    html.Footer([
        html.Div("© 2025 Water Quality Dashboard", style={"fontWeight": "bold"}),
        html.Div([
            "by ",
            html.A("Greg Eastman", href="https://gregeasts.github.io/MyProjects/", target="_blank", style={
                "color": "#2c7a7b",  # Soft emerald tone
                "textDecoration": "none",
                "fontWeight": "bold"
            }),
            ", Emerald Green Power Micro‑Internship 2025"
        ]),
        html.Div("Water Quality Data Analysis Project")
    ], style={
        "textAlign": "center",
        "padding": "20px",
        "backgroundColor": "#e6f2f0",  # Light emerald background
        "fontSize": "14px",
        "color": "#2f4f4f",  # Soft slate text
        "marginTop": "50px",
        "lineHeight": "1.8",
        "boxShadow": "0 -2px 5px rgba(0, 0, 0, 0.1)"
    })
], style={
    "display": "flex",
    "flexDirection": "column",
    "minHeight": "100vh"
})

app.clientside_callback(
    """
    function(search) {
        window.scrollTo(0, 0);
        return null;
    }
    """,
    Output("scroll-store", "data"),
    Input("url", "search")
)

def render_main_layout(mode='Year', test_types=[], parameter='Temperature of Water (°C)', slider_val=0):
    return html.Div([
        html.Div([
            
            dcc.RadioItems(
                id='mode-selector',
                options=[
                    {'label': 'Scroll by Year', 'value': 'Year'},
                    {'label': 'Scroll by Month', 'value': 'Month'}
                ],
                value=mode,
                inline=True,
                style={"marginBottom": "20px"}
            ),
            dcc.Dropdown(
                id='test-type-filter',
                options=[{'label': t.title(), 'value': t} for t in test_types_x],
                multi=True,
                placeholder="Filter by Test Type",
                value=test_types,
                style={"marginTop": "20px", "marginBottom": "20px"}
            ),
            dcc.Dropdown(
                id='parameter-selector',
                options=[{'label': col, 'value': col} for col in cols],
                value=parameter,
                clearable=False,
                style={"marginTop": "10px", "marginBottom": "20px"}
            ),
            html.Label("Minimum Number of Samples:"),
            dcc.Slider(
                id='sample-count-slider',
                min=0,
                max=df['Sample_Count'].max(),
                step=1,
                value=0,
                marks={i: str(i) for i in range(0, df['Sample_Count'].max() + 1, 100)},
                tooltip={"placement": "bottom", "always_visible": False}
            ),
            html.Label("Date: "),
            dcc.Slider(
                id='time-slider',
                step=None,
                marks={0: {"label": "Loading..."}},
                min=0,
                max=0,
                value=slider_val,
            ),
        ], style={"padding": "0px 40px 5px 40px"}),

        dcc.Graph(id='map', style={"height": "600px"}),

        html.Div([
            html.Button("Play", id="play-button", n_clicks=0),
            dcc.Interval(id='interval-component', interval=3000, n_intervals=0, disabled=True)
        ], style={"marginTop": "10px", "textAlign": "center"}),

        html.Div(id='location-info', style={'marginTop': 20, "padding": "10px", "fontSize": "16px"})
    ])

@app.callback(
    Output('interval-component', 'disabled'),
    Output('play-button', 'children'),
    Input('play-button', 'n_clicks'),
    State('interval-component', 'disabled')
)
def toggle_play(n_clicks, disabled):
    if n_clicks % 2 == 1:
        # Odd clicks = playing
        return False, "Pause"
    else:
        # Even clicks = paused
        return True, "Play"




from dash import callback_context

@app.callback(
    Output('store-mode', 'data'),
    Output('store-test-type', 'data'),
    Output('store-parameter', 'data'),
    Output('store-slider', 'data'),
    Input('mode-selector', 'value'),
    Input('test-type-filter', 'value'),
    Input('parameter-selector', 'value'),
    Input('time-slider', 'value'),
)
def save_user_settings(mode, test_types, param, slider_val):
    return mode, test_types, param, slider_val
@callback(
    Output('url', 'search', allow_duplicate=True),
    Input('more-info-button', 'n_clicks'),
    State('more-info-button', 'data-location-id'),
    prevent_initial_call=True
)
def go_to_location_page(n_clicks, location_id):
    if n_clicks:
        return f"?id={location_id}"
    return no_update


from urllib.parse import parse_qs


@app.callback(
    Output('main-content', 'children'),
    Input('url', 'search'),
    State('store-mode', 'data'),
    State('store-test-type', 'data'),
    State('store-parameter', 'data'),
    State('store-slider', 'data')
)
def render_page_content(search, mode, test_types, parameter, slider_val):
    if search:
        params = parse_qs(search.lstrip('?'))
        if 'id' in params:
            location_id = params['id'][0]
            loc = location_info[location_info['Location_ID'] == location_id]
            if loc.empty:
                return html.Div([
                    html.H3("Location not found."),
                    html.Div(html.Button("Home", id="home-button"), style={"position": "absolute", "top": "20px", "right": "20px"})
                ])
            
            loc_data = loc.iloc[0]
            region = df[df['Location_ID'] == location_id]['Region'].iloc[0] if 'Region' in df.columns else 'Unknown'
            sample_count = df[df['Location_ID'] == location_id].shape[0]

            

            return html.Div([
                


                # Info Box
                html.Div([
                    html.H4(f"📍 {loc_data['Location_Name']}", style={"marginBottom": "10px"}),
                    html.P(f"🆔 ID: {location_id}"),
                    html.P(f"🌍 Latitude: {loc_data['Latitude']}"),
                    html.P(f"🌍 Longitude: {loc_data['Longitude']}"),
                    html.P(f"🗺️ Region: {region}"),
                    html.P(f"🧪 Test Types: {loc_data['Test_Type']}"),
                    html.P(f"📊 Number of Samples: {sample_count}"),
                ], style={
                    "position": "absolute",
                    "top": "30px",
                    "left": "30px",
                    "backgroundColor": "white",
                    "padding": "20px",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 8px rgba(0,0,0,0.2)",
                    "zIndex": "10",
                    "maxWidth": "300px",
                    "fontSize": "15px"
                }),

                html.Div(
                    id="long-vertical-box",
                    children=[
                        html.H4("📘 Water Quality Parameter Descriptions", style={"marginBottom": "20px"}),

                        html.Div([
                            html.P([
                                html.Strong("Orthophosphate, reactive as P (mg/l): "),
                                "Orthophosphate is the biologically available form of phosphorus. It is a key nutrient for algae and aquatic plants, and elevated concentrations often indicate agricultural runoff or sewage input. High levels can accelerate eutrophication, causing algal blooms and oxygen depletion in water bodies."
                            ]),
                            html.P([
                                html.Strong("Temperature of Water (°C): "),
                                "Water temperature affects nearly every aspect of aquatic ecosystems, including metabolic rates of organisms, solubility of gases, and chemical reaction rates. Elevated temperatures can reduce dissolved oxygen levels and stress temperature-sensitive species."
                            ]),
                            html.P([
                                html.Strong("Ammoniacal Nitrogen as N (mg/l): "),
                                "This measures the concentration of ammonia and ammonium ions. Ammonia is toxic to aquatic life even at low concentrations and is typically associated with organic pollution from agricultural waste, sewage, or decaying matter."
                            ]),
                            html.P([
                                html.Strong("Phosphorus, Total as P (mg/l): "),
                                "Total phosphorus includes all forms—dissolved and particulate. It provides a broader measure of nutrient enrichment and is crucial for understanding long-term risks of eutrophication in freshwater bodies."
                            ]),
                            html.P([
                                html.Strong("Nitrogen, Total Oxidised as N (mg/l): "),
                                "This parameter includes nitrate and nitrite, the oxidised forms of nitrogen. It is used to assess the impact of fertiliser runoff, wastewater effluent, and atmospheric deposition. High levels may indicate anthropogenic pollution."
                            ]),
                            html.P([
                                html.Strong("Nitrate as N (mg/l): "),
                                "Nitrate is the most stable and commonly found form of nitrogen in oxygenated waters. It originates from agricultural fertilisers, septic systems, and urban runoff. Excessive nitrate can lead to eutrophication and is a human health concern in drinking water."
                            ]),
                            html.P([
                                html.Strong("Nitrite as N (mg/l): "),
                                "Nitrite is an intermediate product in the nitrogen cycle and is typically present at lower concentrations. It can be toxic to aquatic life and is a potential indicator of recent or incomplete nitrification processes."
                            ]),
                            html.P([
                                html.Strong("Nitrogen, Total as N (mg/l): "),
                                "This metric encompasses all forms of nitrogen (organic, ammoniacal, nitrate, and nitrite). It provides an overall assessment of nitrogen loading in a water body, which is important for nutrient management and water quality models."
                            ]),
                            html.P([
                                html.Strong("Alkalinity to pH 4.5 as CaCO3 (mg/l): "),
                                "Alkalinity is a measure of a water body's capacity to neutralize acids and maintain a stable pH. It is largely determined by bicarbonate, carbonate, and hydroxide ions. Low alkalinity makes waters more sensitive to acid rain and pH fluctuations."
                            ]),
                            html.P([
                                html.Strong("pH (phunits): "),
                                "pH measures the hydrogen ion concentration in water. It indicates how acidic or basic the water is, which influences chemical solubility and biological availability. Most aquatic life thrives within a narrow pH range (6.5–8.5)."
                            ]),
                            html.P([
                                html.Strong("Oxygen, Dissolved, % Saturation (%): "),
                                "This represents the amount of dissolved oxygen (DO) relative to the maximum amount water can hold at a given temperature and pressure. Supersaturation can indicate photosynthetic activity, while low saturation suggests possible oxygen depletion."
                            ]),
                            html.P([
                                html.Strong("Oxygen, Dissolved as O2 (mg/l): "),
                                "DO is vital for the respiration of aquatic organisms. It is a key indicator of ecosystem health. Low DO levels (hypoxia) can lead to fish kills and are often caused by organic pollution or thermal stratification."
                            ]),
                            html.P([
                                html.Strong("BOD : 5 Day ATU (mg/l): "),
                                "Biochemical Oxygen Demand over 5 days with allylthiourea (ATU) inhibition measures the amount of oxygen consumed by microorganisms breaking down organic material. It is a proxy for organic pollution and is widely used in wastewater assessment."
                            ]),
                            html.P([
                                html.Strong("Solids, Suspended at 105 C (mg/l): "),
                                "This refers to the amount of particulate matter that remains suspended in the water column and is measured by drying the sample at 105°C. High suspended solids can reduce light penetration, smother habitats, and carry attached pollutants."
                            ])
                        ], style={"fontSize": "13.5px", "lineHeight": "1.7", "paddingRight": "10px", "overflowY": "auto"})
                    ],  # Add your content here later
                    style={
                        "position": "absolute",
                        "top": "400px",
                        "left": "30px",
                        "width": "300px",
                        "maxHeight": "1060px",  # Adjust height as needed
                        "backgroundColor": "#ffffff",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.2)",
                        "overflowY": "auto",
                        "zIndex": 10
                    }
                ),

                # Home Button
                html.Div([
                    html.Button("🏠 Home", id="home-button", style={
                        "backgroundColor": "#2d89ef",
                        "color": "white",
                        "border": "none",
                        "padding": "10px 20px",
                        "borderRadius": "5px",
                        "cursor": "pointer",
                        "fontWeight": "bold"
                    })
                ], style={
                    "position": "absolute",
                    "top": "30px",
                    "right": "30px",
                    "zIndex": "10"
                }),

                # Content Layout Grid
                html.Div([
                    # Top Row: 2 Boxes
                    html.Div([
                        html.Div([
                            html.H2("Complete Data"),
                            html.H5("Metric Selection"),
                            dcc.Dropdown(
                                id='Graph-metric',
                                options=[{'label': t, 'value': t} for t in cols],
                                placeholder="Select Metric to Plot",
                                value='Temperature of Water (°C)',
                                style={"marginTop": "10px", "marginBottom": "20px", "width": "100%"}
                            ),
                            dcc.Checklist(
                                id='remove-anomalies',
                                options=[{'label': 'Remove Anomalies', 'value': 'remove'}],
                                value=[],
                                style={"marginTop": "10px", "marginBottom": "20px"}
                            ),
                            dcc.DatePickerRange(
                                id='date-picker-range',
                                min_date_allowed=datetime.date(2000, 1, 1),
                                max_date_allowed=datetime.date(2025, 12, 31),
                                start_date=datetime.date(2000, 1, 1),
                                end_date=datetime.date(2025, 12, 31),
                                display_format='YYYY-MM-DD',
                                style={"marginTop": "20px", "marginBottom": "20px"}
                            ),
                            dcc.Graph(id='metric-graph')

                        ], style={
                            "width": "100%",
                            "height": "100%",
                            "padding": "20px",
                            "backgroundColor": "white",
                            "borderRadius": "8px",
                            "boxShadow": "0 4px 8px rgba(0,0,0,0.1)"
                        })
                    ], style={"display": "flex", "gap": "5px", "marginTop": "30px"}),

                    # Bottom Row: 3 Boxes
                    html.Div([
                                                # ⬛️ Box 2 layout
                        html.Div([
                            html.H4("🔍 Nearest 5 Sampling Points"),
                            
                            html.Div([
                                html.Label("Minimum Number of Samples"),
                                dcc.Slider(
                                    id="min-sample-slider",
                                    min=0,
                                    max=df['Sample_Count'].max(),
                                    step=1,
                                    value=10,
                                    marks={i: str(i) for i in range(0, df['Sample_Count'].max() + 1, 500)},
                                    tooltip={"placement": "bottom", "always_visible": False}
                                ),
                                html.Br(),

                                html.Label("Filter by Test Type"),
                                dcc.Dropdown(
                                    id="test-type-dropdown",
                                    options=[{'label': t.title(), 'value': t} for t in test_types_x],
                                    multi=True,
                                    placeholder="Select Test Type(s)"
                                )
                            ], style={"marginBottom": "20px"}),

                            html.Div(id="nearest-locations-box")
                        ], style={
                            "width": "30%",
                            "height": "550px",
                            "padding": "20px",
                            
                            "backgroundColor": "#f9f9f9",
                            "borderRadius": "10px",
                            "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                            "overflowY": "auto"
                        }),

                        html.Div(
                            id="metrics-summary-table",
                            style={
                                "backgroundColor": "white",
                                "padding": "20px",
                                "borderRadius": "10px",
                                "boxShadow": "0 4px 10px rgba(0,0,0,0.1)",
                                "height":"550px",
                                "overflowY": "auto"
                                
                            }
                        ),

                        html.Div([
                            html.Div([
                                html.Div("📊", style={"fontSize": "30px", "marginBottom": "5px"}),
                                html.H5("Top 3 Measured Metrics", style={"marginBottom": "10px"}),
                                html.Ul([
                                    html.Li(f"{metric} ({count} samples)")
                                    for metric, count in df[df["Location_ID"] == location_id][cols]
                                    .count()
                                    .sort_values(ascending=False)
                                    .head(3).items()
                                ], style={"paddingLeft": "20px"})
                            ], style={"marginBottom": "25px"}),

                            html.Div([
                                html.Div("📅", style={"fontSize": "30px", "marginBottom": "5px"}),
                                html.H5("Last Recorded Sample", style={"marginBottom": "10px"}),
                                html.P(
                                    df[df["Location_ID"] == location_id]["Date"].max().strftime("%d %b %Y"),
                                    style={"fontSize": "16px"}
                                )
                            ], style={"marginBottom": "25px"}),

                            html.Div([
                                html.Div("⏱️", style={"fontSize": "30px", "marginBottom": "5px"}),
                                html.H5("Sample Interval Range", style={"marginBottom": "10px"}),

                                html.P(
                                    f"Min Gap: {int(df[df['Location_ID'] == location_id]['Date'].sort_values().diff().dt.days.dropna().min())} days",
                                    style={"marginBottom": "5px"}
                                ),
                                html.P(
                                    f"Max Gap: {int(df[df['Location_ID'] == location_id]['Date'].sort_values().diff().dt.days.dropna().max())} days"
                                )
                            ])
                        ], style={
                            
                            "height": "550px",
                            "backgroundColor": "#f2f2f2",
                            "padding": "20px",
                            "borderRadius": "8px",
                            "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                            "overflowY": "auto"
                        }),


                    ], style={"display": "flex", "gap": "10px", "marginTop": "20px", "padding": "20px"})
                    
                ], style={"marginLeft": "390px", "marginRight": "5px", "marginBottom": "20px"}),
                # Bottom Full-Width Row: Two Half-Width Empty Boxes
                html.Div([
                    # Left Box
                    html.Div([
                        html.H4("📍 Monthly Smoothed Averages by Location"),
                        
                        dcc.Dropdown(
                            id='monthly-metric-dropdown',
                            options=[{'label': t, 'value': t} for t in cols],
                            value=cols[0],
                            style={"marginBottom": "10px"}
                        ),
                        
                        dcc.Graph(id='monthly-avg-graph', style={"height": "450px"}),
                        
                        html.Div(id='yearly-metric-display', style={
                            "marginTop": "20px",
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "color": "#333"
                        }),
                    ], style={
                        "width": "49%",
                        "height": "600px",
                        "backgroundColor": "#ffffff",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                        "overflowY": "auto"
                    }),

                    # Right Box
                    html.Div([
                        html.Div(id='monthly-image', style={"width": "100%", "height": "450px"}),

                        html.H4("Metric Trends", style={
                            "marginTop": "10px",
                            "marginBottom": "5px",
                            "fontWeight": "bold"
                        }),

                        html.Div(
                            "Via K-means clustering, ID's with enough data for a metric are categorised into one of the above seven graph shapes, by the shape they are most similar to. The number below the graph on the left corresponds to the cluster the current ID is within for the metric.",
                            style={
                                "fontSize": "14px",
                                "color": "#555",
                                "padding": "0 10px 10px 10px"
                            }
                        ),
                        dash_table.DataTable(
                            id='monthly-category-table',
                            
                            style_table={'marginTop': '20px', 'overflowX': 'auto','width': '100%','margin':'0 auto'},
                            style_cell={'textAlign': 'center', 'padding': '8px'},
                            style_header={
                                'backgroundColor': '#f4f4f4',
                                'fontWeight': 'bold',
                                'maxWidth': '80%',
                                'overflowX':'auto',
                                'margin':'0 auto'
                            },
                            
                            

                        )

                    ], id='monthly-image-container', style={
                        "width": "49%",
                        "height": "600px",
                        "backgroundColor": "#ffffff",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                        "overflowY": "auto",
                        "textAlign": "center",
                        "display": "flex",
                        "flexDirection": "column",
                        "alignItems": "center"
                    })

                ], style={
                    "display": "flex",
                    "gap": "2%",
                    "marginLeft": "30px",
                    "marginRight": "30px",
                    "marginTop": "30px",
                    "marginBottom": "60px"
                }),

                html.Div([
                    # Left Box
                    html.Div([
                        html.H4("📍 Over Time Smoothed Averages by Location"),
                        
                        dcc.Dropdown(
                            id='over_time-metric-dropdown',
                            options=[{'label': t, 'value': t} for t in cols],
                            value=cols[0],
                            style={"marginBottom": "10px"}
                        ),

                        dcc.Graph(id='over_time-avg-graph', style={"height": "450px"}),

                        html.Div(id='over_time-metric-display', style={
                            "marginTop": "20px",
                            "fontSize": "16px",
                            "fontWeight": "bold",
                            "color": "#333"
                        }),
                    ], style={
                        "width": "49%",
                        "height": "600px",
                        "backgroundColor": "#ffffff",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                        "overflowY": "auto"
                    }),

                    # Right Box
                    html.Div([
                        # Placeholder content (you can replace this with a map, image, etc.)
                        html.Div(id='over-time-image', style={"width": "100%", "height": "450px"}),

                        html.H4("Metric Trends", style={
                            "marginTop": "10px",
                            "marginBottom": "5px",
                            "fontWeight": "bold"
                        }),

                        html.Div(
                            "Via K-means clustering, ID's with enough data for a metric are categorised into one of the above seven graph shapes, by the shape they are most similar to. The number below the graph on the left corresponds to the cluster the current ID is within for the metric.",
                            style={
                                "fontSize": "14px",
                                "color": "#555",
                                "padding": "0 10px 10px 10px"
                            }
                        ),
                        dash_table.DataTable(
                            id='over_time-category-table',
                            
                            style_table={'marginTop': '20px', 'overflowX': 'auto','width': '100%','margin':'0 auto'},
                            style_cell={'textAlign': 'center', 'padding': '8px'},
                            style_header={
                                'backgroundColor': '#f4f4f4',
                                'fontWeight': 'bold',
                                'maxWidth': '80%',
                                'overflowX':'auto',
                                'margin':'0 auto'
                            },
                            
                            

                        )

                    ], style={
                        "width": "49%",
                        "height": "600px",
                        "backgroundColor": "#ffffff",
                        "padding": "20px",
                        "borderRadius": "10px",
                        "boxShadow": "0 4px 8px rgba(0,0,0,0.1)",
                        "overflowY": "auto",
                        "textAlign": "center",
                        "display": "flex",
                        "flexDirection": "column",
                        "alignItems": "center"
                    })

                ], style={
                    "display": "flex",
                    "gap": "2%",
                    "marginLeft": "30px",
                    "marginRight": "30px",
                    "marginTop": "10px",
                    "marginBottom": "20px"
                }),
                html.Div([
                    html.Div(id='graph-resize-trigger', style={"display": "none"}),
                    html.H4("📍 Comparison Graphing Tool", style={
                        "marginBottom": "15px",
                        "fontWeight": "bold",
                        "textAlign": "center",
                        "fontSize":"40px"
                    }),
                    
                    dcc.Store(id='selected-locations-store',data=[]),

                    # Dropdown to filter by Test_Type
                    
                    html.Div([

                        html.Div([
                            dcc.Dropdown(
                                id='location_test-type-filter',
                                options=[{'label': t.title(), 'value': t} for t in test_types_x],
                                multi=True,
                                placeholder="Filter by Test Type",
                                value=test_types,
                                style={"marginTop": "20px", "marginBottom": "20px"}
                            ),

                            html.Label("Minimum Number of Samples:"),
                            dcc.Slider(
                                id='location_sample-count-slider',
                                min=0,
                                max=df['Sample_Count'].max(),
                                step=1,
                                value=0,
                                marks={i: str(i) for i in range(0, df['Sample_Count'].max() + 1, 500)},
                                tooltip={"placement": "bottom", "always_visible": False}
                            ),
                            # Map
                            dcc.Graph(id='location_map',config={"responsive": True}, style={
                                "width": "100%",
                                "height": "500px",
                                
                            }),
                        ], style={
                            "width": "35%",
                            "padding": "15px",
                            "height":"700px",
                        }),

                        html.Div([
                            html.H4("📍 Selected Locations"),
                            html.Div(id='selected-locations-list', style={"marginTop": "10px"})
                        ], style={
                            "width": "15%",
                            "height": "700px",
                            
                            "backgroundColor": "#f9f9f9",
                            "padding": "15px",
                            "borderRadius": "10px",
                            "boxShadow": "0 2px 6px rgba(0,0,0,0.1)",
                            "overflowY": "auto"
                        }),
                         html.Div([
                            html.H4("📍 Comparison Map"),
                            dcc.RadioItems(
                                id='type-selector',
                                options=[
                                    {'label': 'Monthly Avg', 'value': 'Monthly'},
                                    {'label': 'Yearly Avg', 'value': 'Yearly'},
                                    {'label': 'All Data', 'value': 'All'},
                                ],

                                value=mode,
                                inline=True,
                                style={"marginBottom": "20px"}
                            ),
                            dcc.Checklist(
                                id='remove-anomalies1',
                                options=[{'label': 'Remove Anomalies', 'value': 'remove'}],
                                value=[],
                                style={"marginTop": "10px", "marginBottom": "20px"}
                            ),
                            dcc.Checklist(
                                id='graph-toggle-checklist',
                                options=[
                                    {'label': 'Show Raw Data', 'value': 'raw'},
                                    {'label': 'Show LOWESS', 'value': 'lowess'}
                                ],
                                value=['raw', 'lowess'],  # Default: both visible
                                labelStyle={'display': 'inline-block', 'margin-right': '10px'}
                            ),
                            dcc.Dropdown(
                                id='comparison-metric-dropdown',
                                options=[{'label': t, 'value': t} for t in cols],
                                value=cols[0],
                                style={"marginBottom": "10px"}
                            ),

                            dcc.Graph(id='comparison-graph')
                            
                        ], style={
                            "width": "80%",
                            "height": "700px",
                            "backgroundColor": "#f9f9f9",
                            "padding": "15px",
                            "borderRadius": "10px",
                            "boxShadow": "0 2px 6px rgba(0,0,0,0.1)",
                            "overflowY": "auto"
                        }),

                        
                    ], style={
                        "display": "flex",
                        "width": "95%",
                        "gap":"1%",
                        "margin": "0 auto",
                        
                        "height":"650px"

                    })

                    
                ],
                    style={
                        "width": "100%",
                        "marginTop": "40px",
                        "marginLeft": "0px",
                        "marginRight": "0px",
                        "marginBottom": "60px"
                    }
                )

                
                

            ])
            
    
    # Default back to home/main layout if no ID
    return render_main_layout(
        mode or 'Year',
        test_types or [],
        parameter or 'Temperature of Water (°C)',
        slider_val or 0
    )

app.clientside_callback(
    """
    function(n_clicks) {
        setTimeout(() => {
            window.dispatchEvent(new Event('resize'));
        }, 100);
        return '';
    }
    """,
    Output('graph-resize-trigger', 'children'),
    Input('location_map', 'figure')  # or use Input('url', 'href') for on-load trigger
)



from dash import callback, Input, Output
import plotly.graph_objects as go
from statsmodels.nonparametric.smoothers_lowess import lowess
import datetime
import pandas as pd
import numpy as np
from urllib.parse import parse_qs

@app.callback(
    Output('comparison-graph', 'figure'),
    Input('type-selector', 'value'),
    Input('url', 'search'),
    Input('remove-anomalies1', 'value'),
    Input('selected-locations-store', 'data'),
    Input('comparison-metric-dropdown', 'value'),
    Input('graph-toggle-checklist', 'value')
)
def update_comparison_graph(view_type, search, remove_flagged, selected_locations, selected_metric,graph_layers):
    if not view_type or not search or not selected_metric:
        return go.Figure()

    params = parse_qs(search.lstrip('?'))
    main_id = params.get('id', [None])[0]
    if not main_id:
        return go.Figure()

    all_ids = [main_id] + [id_ for id_ in selected_locations if id_ != main_id]

    fig = go.Figure()

    for loc_id in all_ids:
        df_loc = df[df['Location_ID'] == loc_id]
        df_loc['Date'] = pd.to_datetime(df_loc['Date'])
        df_loc = df_loc.sort_values(by='Date')

        flagged_col = f"{selected_metric}_flagged"
        has_flagged = flagged_col in df_loc.columns

        if has_flagged:
            anomalies = df_loc[df_loc[flagged_col]]
            normals = df_loc[~df_loc[flagged_col]]
        else:
            anomalies = df_loc.iloc[0:0]
            normals = df_loc

        if 'remove' in remove_flagged:
            df_plot = normals
            anomalies = df_plot.iloc[0:0]
        else:
            df_plot = pd.concat([normals, anomalies]).sort_values(by='Date')

        is_main = loc_id == main_id
        line_width = 3 if is_main else 2
        dash_style = 'solid'
        marker_size = 3 if is_main else 2

        # === "All" View ===
        if view_type == 'All':
            valid = df_plot.dropna(subset=[selected_metric])
            if 'raw' in graph_layers:
                fig.add_trace(go.Scatter(
                    x=valid['Date'],
                    y=valid[selected_metric],
                    mode='lines+markers',
                    name=f"{loc_id} (raw)",
                    line=dict(width=line_width),
                    marker=dict(size=marker_size)
                ))

            if not anomalies.empty and has_flagged and 'remove' not in remove_flagged:
                anomalies_valid = anomalies.dropna(subset=[selected_metric])
                if 'raw' in graph_layers:
                    fig.add_trace(go.Scatter(
                        x=anomalies_valid['Date'],
                        y=anomalies_valid[selected_metric],
                        mode='markers',
                        name=f"{loc_id} Anomalies",
                        marker=dict(color='red', size=8, symbol='circle-open')
                    ))

            if not valid.empty:
                smoothed = lowess(
                    valid[selected_metric],
                    valid['Date'].map(datetime.datetime.toordinal),
                    frac=0.5
                )
                if 'lowess' in graph_layers and not df.empty:
                    fig.add_trace(go.Scatter(
                        x=pd.to_datetime([datetime.date.fromordinal(int(x)) for x in smoothed[:, 0]]),
                        y=smoothed[:, 1],
                        mode='lines',
                        name=f"{loc_id} (LOWESS)",
                        line=dict(width=line_width + 1, dash=dash_style)
                    ))

        # === "Yearly" View ===
        elif view_type == 'Yearly':
            df_plot['Year'] = df_plot['Date'].dt.year
            yearly_avg = df_plot.dropna(subset=[selected_metric]).groupby('Year')[selected_metric].mean().reset_index()

            if yearly_avg.empty:
                continue

            smoothed = lowess(yearly_avg[selected_metric], yearly_avg['Year'], frac=0.5)
            yearly_avg['Smoothed'] = smoothed[:, 1]
            if 'raw' in graph_layers:
                fig.add_trace(go.Scatter(
                    x=yearly_avg['Year'],
                    y=yearly_avg[selected_metric],
                    mode='lines+markers',
                    name=f"{loc_id} (yearly avg)",
                    line=dict(width=line_width),
                    marker=dict(size=marker_size)
                ))
            if 'lowess' in graph_layers and not df.empty:
                fig.add_trace(go.Scatter(
                    x=yearly_avg['Year'],
                    y=yearly_avg['Smoothed'],
                    mode='lines',
                    name=f"{loc_id} (LOWESS)",
                    line=dict(width=line_width + 1, dash=dash_style)
                ))

        # === "Monthly" View ===
        elif view_type == 'Monthly':
            df_plot['Month'] = df_plot['Date'].dt.month
            monthly_avg = df_plot.dropna(subset=[selected_metric]).groupby('Month')[selected_metric].mean().reset_index()

            if monthly_avg.empty:
                continue

            smoothed = lowess(monthly_avg[selected_metric], monthly_avg['Month'], frac=0.5)
            monthly_avg['Smoothed'] = smoothed[:, 1]
            if 'raw' in graph_layers:
                fig.add_trace(go.Scatter(
                    x=monthly_avg['Month'],
                    y=monthly_avg[selected_metric],
                    mode='lines+markers',
                    name=f"{loc_id} (monthly avg)",
                    line=dict(width=line_width),
                    marker=dict(size=marker_size)
                ))
            if 'lowess' in graph_layers and not df.empty:
                fig.add_trace(go.Scatter(
                    x=monthly_avg['Month'],
                    y=monthly_avg['Smoothed'],
                    mode='lines',
                    name=f"{loc_id} (LOWESS)",
                    line=dict(width=line_width + 1, dash=dash_style)
                ))

    # Layout
    fig.update_layout(
        title=f"{selected_metric} ({view_type}) Comparison",
        xaxis_title="Date" if view_type == 'All' else view_type,
        yaxis_title=selected_metric,
        template="plotly_white",
        height=500,
        margin={"t": 40, "b": 40, "l": 40, "r": 40},
        legend_title="Location",
        legend=dict(
            font=dict(size=8),           # Smaller font
            itemsizing='constant',        # Prevents marker size from affecting legend item size
            tracegroupgap=0,              # Less vertical gap
            itemwidth=30                  # Shrinks reserved width for legend text (useful in horizontal legends)
        )
    )

    return fig





@app.callback(
    Output('metric-graph', 'figure'),
    Input('Graph-metric', 'value'),
    Input('url', 'search'),
    Input('remove-anomalies', 'value'),
    Input('date-picker-range', 'start_date'),
    Input('date-picker-range', 'end_date'),
)
def update_metric_graph(selected_metrics, search, remove_flagged, start_date, end_date):
    if not selected_metrics or not search:
        return go.Figure()

    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]
    if not location_id:
        return go.Figure()

    filtered = df[df['Location_ID'] == location_id].sort_values(by='Date')
    filtered['Date'] = pd.to_datetime(filtered['Date'])

    # Filter by date range
    if start_date:
        filtered = filtered[filtered['Date'] >= pd.to_datetime(start_date)]
    if end_date:
        filtered = filtered[filtered['Date'] <= pd.to_datetime(end_date)]

    flagged_col = f"{selected_metrics}_flagged"
    has_flagged = flagged_col in filtered.columns

    # Separate normal and anomaly data (if flag column exists)
    if has_flagged:
        anomalies = filtered[filtered[flagged_col]]
        normals = filtered[~filtered[flagged_col]]
    else:
        anomalies = filtered.iloc[0:0]
        normals = filtered

    # If 'remove' is checked, exclude anomalies from both plot and smoothing
    if 'remove' in remove_flagged:
        filtered = normals
        anomalies = filtered.iloc[0:0]  # clear anomalies from plot
    else:
        filtered = pd.concat([normals, anomalies]).sort_values(by='Date')

    # 📈 Build the figure
    fig = go.Figure()

    valid = filtered.dropna(subset=[selected_metrics])

    # Plot raw data as line+markers
    fig.add_trace(go.Scatter(
        x=valid['Date'],
        y=valid[selected_metrics],
        mode='lines+markers',
        name=f"{selected_metrics} (raw)",
        line=dict(color='blue'),
        marker=dict(color='blue')
    ))

    # Plot anomaly points separately in red (if not removed)
    if not anomalies.empty and has_flagged and 'remove' not in remove_flagged:
        anomalies_valid = anomalies.dropna(subset=[selected_metrics])
        fig.add_trace(go.Scatter(
            x=anomalies_valid['Date'],
            y=anomalies_valid[selected_metrics],
            mode='markers',
            name='Anomalies',
            marker=dict(color='red', size=8, symbol='circle-open')
        ))

    # Apply LOWESS smoothing
    if not valid.empty:
        smoothed = lowess(
            valid[selected_metrics],
            valid['Date'].map(datetime.datetime.toordinal),
            frac=0.5
        )
        fig.add_trace(go.Scatter(
            x=pd.to_datetime([datetime.date.fromordinal(int(x)) for x in smoothed[:, 0]]),
            y=smoothed[:, 1],
            mode='lines',
            name=f"{selected_metrics} (LOWESS)",
            line=dict(color='red', width=4, dash='solid')
        ))

    # Final layout
    fig.update_layout(
        title=f"{selected_metrics} over Time for Location ID {location_id}",
        margin=dict(t=40, b=40, l=40, r=40),
        xaxis_title='Date',
        yaxis_title='Value'
    )

    return fig
@app.callback(
    Output("metrics-summary-table", "children"),
    Input("url", "search")
)
def update_metrics_summary_table(search):
    if not search:
        return html.Div("No data.")

    params = parse_qs(search.lstrip("?"))
    location_id = params.get("id", [None])[0]
    if not location_id:
        return html.Div("No location selected.")

    subset = df[df["Location_ID"] == location_id]
    if subset.empty:
        return html.Div("No data found for this location.")

    data = []
    for col in cols:
        flagged_col = f"{col}_flagged"
        n_valid = subset[col].notna().sum()
        n_flagged = subset[flagged_col].sum() if flagged_col in subset.columns else 0
        data.append({
            "Metric": col,
            "Valid Count": n_valid,
            "Flagged Count": n_flagged
        })

    return dash_table.DataTable(
        columns=[
            {"name": "Metric", "id": "Metric"},
            {"name": "Valid Data", "id": "Valid Count"},
            {"name": "Anomalies", "id": "Flagged Count"}
        ],
        data=data,
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "padding": "8px"},
        style_header={
            "backgroundColor": "rgb(230, 230, 230)",
            "fontWeight": "bold"
        },
        style_as_list_view=True
    )


@app.callback(
    Output('monthly-image', 'children'),
    Input('monthly-metric-dropdown', 'value')
)
def update_image(selected_metric):
    if selected_metric not in cols:
        return "No image available."

    # Find index of selected metric
    idx = cols.index(selected_metric)
    
    # Build image filename assuming they are named as "0.png", "1.png", etc.
    # Adjust extension if your images are jpg, jpeg, etc.
    filename = f"monthly_img/{idx}.png"

    # Just in case, verify if file exists in assets (optional)
    # In Dash, any files in assets/ folder are served automatically
    # So we just need to set src to /assets/monthly_img/{idx}.png
    # The URL path inside assets is relative, so src="/assets/monthly_img/0.png"

    img_src = f"/assets/{filename}"

    return html.Img(src=img_src, style={"maxWidth": "100%", "maxHeight": "100%", "objectFit": "contain"})

@callback(
    Output('selected-locations-store', 'data',allow_duplicate=True),
    
    Input('location_map', 'clickData'),
    State('selected-locations-store', 'data'),
    State('url', 'search'),
    prevent_initial_call=True
)
def store_selected_locations(clickData, selected_ids, search):
    from urllib.parse import parse_qs
    print(selected_ids)
    params = parse_qs(search.lstrip("?"))
    current_id = params.get("id", [None])[0]
    


    if not clickData:
        return selected_ids

    clicked_id = clickData['points'][0]['text']
    print(f"Existing IDs: {selected_ids}, Clicked: {clicked_id}, Current: {current_id}")
    if not selected_ids:
        selected_ids = []

    # Ensure no duplicates, and don't add the current selected location
    if clicked_id != current_id and clicked_id not in selected_ids:
        return selected_ids + [clicked_id]
    
    return selected_ids

@app.callback(
    Output('over-time-image', 'children'),
    Input('over_time-metric-dropdown', 'value')
)
def update_image_1(selected_metric):
    if selected_metric not in cols:
        return "No image available."

    # Find index of selected metric
    idx = cols.index(selected_metric)
    
    # Build image filename assuming they are named as "0.png", "1.png", etc.
    # Adjust extension if your images are jpg, jpeg, etc.
    filename = f"over-time_img/{idx+1}_1.png"

    # Just in case, verify if file exists in assets (optional)
    # In Dash, any files in assets/ folder are served automatically
    # So we just need to set src to /assets/monthly_img/{idx}.png
    # The URL path inside assets is relative, so src="/assets/monthly_img/0.png"

    img_src = f"/assets/{filename}"

    return html.Img(src=img_src, style={"maxWidth": "100%", "maxHeight": "100%", "objectFit": "contain"})

@app.callback(
    Output('over_time-category-table', 'data'),
    Output('over_time-category-table', 'columns'),
    Output('over_time-category-table', 'style_data_conditional'),
    Input('over_time-metric-dropdown', 'value'),
    Input('url', 'search')  # assuming you're using URL-based ID passing
)
def update_category_table(metric, search):
    from urllib.parse import parse_qs
    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]

    if location_id is None or metric is None:
        return [], [],[]

    # Filter by location
    df_loc = df[df['Location_ID'] == location_id]

    # Extract relevant test types used at this location
    split_test_types = (
        df_loc['Test_Type']
        .dropna()
        .str.lower()
        .str.split(',')
        .explode()
        .str.strip()
        .unique()
    )
    test_type_set = set(split_test_types)

    cluster_col = f"{metric}_shape_over-time"
    if cluster_col not in df.columns:
        return [], [],[]

    try:
        # Clean and filter original df for matching test types
        df_filtered = df[df['Test_Type'].notna()]
        df_filtered['Test_Type_clean'] = df_filtered['Test_Type'].str.lower().str.strip()

        df_filtered = df_filtered[df_filtered['Test_Type_clean'].isin(test_type_set)]
        df_filtered = df_filtered.groupby('Location_ID', as_index=False).first()

        # Group and pivot
        grouped = (
            df_filtered
            .groupby(['Test_Type', cluster_col])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
       

        # Ensure cluster columns are ordered (0 to 6)
        cluster_cols = []
        for col in grouped.columns:
            try:
                cluster_num = int(float(col))  # Handles both '0.0' and 0
                cluster_cols.append((cluster_num, col))
            except (ValueError, TypeError):
                continue

        # Sort by cluster number
        cluster_cols = sorted(cluster_cols, key=lambda x: x[0])


# Identify max cluster column per row 

        # Rebuild ordered list: 'Test_Type_clean' + ordered cluster columns
        ordered_cols = ['Test_Type'] + [col for _, col in cluster_cols]
        grouped = grouped[ordered_cols]
    
        # Rename columns: Cluster 1–7
        clusters=[f"Cluster {i+1}" for i, _ in enumerate(cluster_cols)]
        new_column_names = ['Test Type'] + [f"Cluster {i+1}" for i, _ in enumerate(cluster_cols)]
        grouped.columns = new_column_names
    
        grouped['Max_Cluster'] = grouped[clusters].idxmax(axis=1)
        
        style_data_conditional = [
            {
                'if': {
                    'filter_query': f'{{Max_Cluster}} = "{col}"',
                    'column_id': col
                },
                'backgroundColor': '#D2F3FF',
                'fontWeight': 'bold'
            }
            for col in clusters
        ]

        # Build table data and columns for Dash
        columns = [{"name": col, "id": col} for col in grouped.columns]
        data = grouped.to_dict("records")
        return data, columns, style_data_conditional

    except Exception as e:
        print("Error:", e)
        return [], [],[]

@callback(
    Output('selected-locations-list', 'children'),
    Input('selected-locations-store', 'data'),
)
def render_selected_list(selected_ids):
    print("render_selected_list fired with:", selected_ids)
    if not selected_ids:
        return html.Div("No locations selected.")
    

    return [
        html.Div([
            html.Span(loc_id, style={"marginRight": "10px"}),
            html.Button("❌", id={'type': 'remove-button', 'index': loc_id}, n_clicks=0)
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "5px"})
        for loc_id in selected_ids
    ]

@callback(
    Output('selected-locations-store', 'data', allow_duplicate=True),
    Input({'type': 'remove-button', 'index': ALL}, 'n_clicks'),
    State('selected-locations-store', 'data'),
    prevent_initial_call=True
)
def remove_location(n_clicks_list, selected_ids):
    triggered = ctx.triggered_id
    print("Triggered:", triggered)
    print("n_clicks_list:", n_clicks_list)
    
    if not triggered or not isinstance(triggered, dict) or triggered.get('type') != 'remove-button':
        return no_update
    
    # Find the index in the list corresponding to the triggered button
    # Input IDs have this format: {'type': 'remove-button', 'index': some_id}
    # We need to find which position in n_clicks_list corresponds to the triggered['index']
    triggered_index = None
    for i, input_id in enumerate(ctx.inputs_list[0]):
        # input_id is a dict like {'id': {'type': 'remove-button', 'index': ...}, 'property': 'n_clicks'}
        if input_id['id']['index'] == triggered['index']:
            triggered_index = i
            break

    if triggered_index is None:
        print("Triggered index not found in inputs_list!")
        return no_update

    # Check the clicks value at that index
    if n_clicks_list[triggered_index] == 0 or n_clicks_list[triggered_index] is None:
        print("Triggered button has zero clicks, ignoring")
        return no_update

    selected_ids = selected_ids or []
    removed_id = triggered['index']
    new_selected = [id_ for id_ in selected_ids if id_ != removed_id]
    print(f"Removing {removed_id}: New list:", new_selected)
    return new_selected
@app.callback(
    Output('monthly-category-table', 'data'),
    Output('monthly-category-table', 'columns'),
    Output('monthly-category-table', 'style_data_conditional'),
    Input('monthly-metric-dropdown', 'value'),
    Input('url', 'search')  # assuming you're using URL-based ID passing
)
def update_category_table1(metric, search):
    from urllib.parse import parse_qs
    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]

    if location_id is None or metric is None:
        return [], [],[]

    # Filter by location
    df_loc = df[df['Location_ID'] == location_id]

    # Extract relevant test types used at this location
    split_test_types = (
        df_loc['Test_Type']
        .dropna()
        .str.lower()
        .str.split(',')
        .explode()
        .str.strip()
        .unique()
    )
    test_type_set = set(split_test_types)

    cluster_col = f"{metric}_shape_yearly"
    if cluster_col not in df.columns:
        return [], [],[]

    try:
        # Clean and filter original df for matching test types
        df_filtered = df[df['Test_Type'].notna()]
        df_filtered['Test_Type_clean'] = df_filtered['Test_Type'].str.lower().str.strip()

        df_filtered = df_filtered[df_filtered['Test_Type_clean'].isin(test_type_set)]
        df_filtered = df_filtered.groupby('Location_ID', as_index=False).first()

        # Group and pivot
        grouped = (
            df_filtered
            .groupby(['Test_Type', cluster_col])
            .size()
            .unstack(fill_value=0)
            .reset_index()
        )
       

        # Ensure cluster columns are ordered (0 to 6)
        cluster_cols = []
        for col in grouped.columns:
            try:
                cluster_num = int(float(col))  # Handles both '0.0' and 0
                cluster_cols.append((cluster_num, col))
            except (ValueError, TypeError):
                continue

        # Sort by cluster number
        cluster_cols = sorted(cluster_cols, key=lambda x: x[0])


# Identify max cluster column per row 

        # Rebuild ordered list: 'Test_Type_clean' + ordered cluster columns
        ordered_cols = ['Test_Type'] + [col for _, col in cluster_cols]
        grouped = grouped[ordered_cols]
    
        # Rename columns: Cluster 1–7
        clusters=[f"Cluster {i+1}" for i, _ in enumerate(cluster_cols)]
        new_column_names = ['Test Type'] + [f"Cluster {i+1}" for i, _ in enumerate(cluster_cols)]
        grouped.columns = new_column_names
       
        grouped['Max_Cluster'] = grouped[clusters].idxmax(axis=1)
      
        style_data_conditional = [
            {
                'if': {
                    'filter_query': f'{{Max_Cluster}} = "{col}"',
                    'column_id': col
                },
                'backgroundColor': '#D2F3FF',
                'fontWeight': 'bold'
            }
            for col in clusters
        ]

        # Build table data and columns for Dash
        columns = [{"name": col, "id": col} for col in grouped.columns]
        data = grouped.to_dict("records")
        return data, columns, style_data_conditional

    except Exception as e:
        print("Error:", e)
        return [], [],[]


@app.callback(
    Output('over_time-avg-graph', 'figure'),
    Input('over_time-metric-dropdown', 'value'),
    State('url', 'search')  # or however you're passing search param
)
def update_over_time_avg_graph(metric, search):
    
    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]

    Flagged =  f'{metric}_flagged'

    if location_id is None:
        
        return go.Figure()

    df_loc = df[(df['Location_ID'] == location_id) & (~df[Flagged]) & (df[metric].notna())]

    # Group by Month
    
    monthly_avg = df_loc.groupby('Year')[metric].mean().reset_index()
    monthly_avg = monthly_avg.dropna(subset=[metric])
   

    # LOWESS smoothing
 
    smoothed = lowess(monthly_avg[metric], monthly_avg['Year'].astype(np.int64), frac=0.5)
    monthly_avg['Smoothed'] = smoothed[:, 1]

    # Plot
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly_avg['Year'], y=monthly_avg[metric],
        mode='lines+markers', name='Monthly Average',
        hoverinfo='x+y',
    ))
    fig.add_trace(go.Scatter(
        x=monthly_avg['Year'], y=monthly_avg['Smoothed'],
        mode='lines', name='LOWESS Smoothed', line=dict(dash='dash'),
        hoverinfo='x+y',
    ))

    fig.update_layout(
        height=450,
        margin={"t": 20, "b": 40, "l": 40, "r": 20},
        xaxis_title="Year",
        yaxis_title=metric,
        template="plotly_white",
        
    )

    return fig


@app.callback(
    Output('monthly-avg-graph', 'figure'),
    Input('monthly-metric-dropdown', 'value'),
    State('url', 'search')  # or however you're passing search param
)
def update_monthly_avg_graph(metric, search):

    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]

    Flagged =  f'{metric}_flagged'

    if location_id is None:
        
        return go.Figure()

    df_loc = df[(df['Location_ID'] == location_id) & (~df[Flagged]) & (df[metric].notna())]
  
    # Group by Month
    
    monthly_avg = df_loc.groupby('Month')[metric].mean().reset_index()
    monthly_avg = monthly_avg.dropna(subset=[metric])
   

    # LOWESS smoothing
 
    smoothed = lowess(monthly_avg[metric], monthly_avg['Month'].astype(np.int64), frac=0.5)
    monthly_avg['Smoothed'] = smoothed[:, 1]

    # Plot
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=monthly_avg['Month'], y=monthly_avg[metric],
        mode='lines+markers', name='Monthly Average',
        hoverinfo='x+y',
    ))
    fig.add_trace(go.Scatter(
        x=monthly_avg['Month'], y=monthly_avg['Smoothed'],
        mode='lines', name='LOWESS Smoothed', line=dict(dash='dash'),
        hoverinfo='x+y',
    ))

    fig.update_layout(
        height=450,
        margin={"t": 20, "b": 40, "l": 40, "r": 20},
        xaxis_title="Month",
        yaxis_title=metric,
        template="plotly_white",
        
    )

    return fig

@app.callback(
    Output('yearly-metric-display', 'children'),
    Input('monthly-metric-dropdown', 'value'),
    Input('url', 'search')
)
def update_yearly_metric_display(metric, search):
    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]

    if location_id is None:
        return ""

    yearly_col = f'{metric}_shape_yearly'

    # Filter df for the location and check if yearly_col exists
    df_loc = df[df['Location_ID'] == location_id]

    if yearly_col not in df.columns or df_loc.empty:
        return "Not enough data points to categorise"

    # Get the unique yearly value for that location (assuming it's the same for all rows)
    yearly_vals = df_loc[yearly_col].dropna().unique()

    if len(yearly_vals) == 0:
        return "Not enough data points to categorise"

    # If multiple unique values, decide how to handle; here just take the first
    yearly_val = yearly_vals[0]

    # Check if yearly_val indicates "Unidentified" or similar
    if yearly_val == "Unidentified":
        return "Not enough data points to categorise curve"

    return f"Categorical value for {metric} curve: {str(float(yearly_val)+1)}"


@app.callback(
    Output('over_time-metric-display', 'children'),
    Input('over_time-metric-dropdown', 'value'),
    Input('url', 'search')
)
def update_yearly_metric_display(metric, search):
    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]

    if location_id is None:
        return ""

    yearly_col = f'{metric}_shape_over-time'

    # Filter df for the location and check if yearly_col exists
    df_loc = df[df['Location_ID'] == location_id]

    if yearly_col not in df.columns or df_loc.empty:
        return "Not enough data points to categorise"

    # Get the unique yearly value for that location (assuming it's the same for all rows)
    yearly_vals = df_loc[yearly_col].dropna().unique()

    if len(yearly_vals) == 0:
        return "Not enough data points to categorise"

    # If multiple unique values, decide how to handle; here just take the first
    yearly_val = yearly_vals[0]

    # Check if yearly_val indicates "Unidentified" or similar
    if yearly_val == "Unidentified":
        return "Not enough data points to categorise curve"

    return f"Categorical value for {metric} curve: {str(float(yearly_val)+1)}"


@app.callback(
    Output('url', 'search',allow_duplicate=True),
    Input('home-button', 'n_clicks'),
    prevent_initial_call=True
)
def go_home(n_clicks):
    if n_clicks:
        return ""
    return no_update


def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # km
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1 
    dlon = lon2 - lon1 
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a)) 
    return R * c

@app.callback(
    Output("nearest-locations-box", "children"),
    Input("min-sample-slider", "value"),
    Input("test-type-dropdown", "value"),
    Input("url", "search"),
)
def update_nearest_locations(min_samples, selected_types, search):
    if not search:
        return "No location selected."

    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]
    if not location_id:
        return "Invalid location ID."

    # Selected location
    current = location_info[location_info['Location_ID'] == location_id]
    if current.empty:
        return "Location not found."
    cur_lat = current.iloc[0]['Latitude']
    cur_lon = current.iloc[0]['Longitude']

    # Filter by test type and sample count
    filtered = location_info[location_info['Location_ID'] != location_id]
    if selected_types:
            pattern = '|'.join([fr'\b{t}\b' for t in selected_types])
            filtered = filtered[filtered['Test_Type'].str.contains(pattern, case=False, na=False, regex=True)]
    if min_samples:

        filtered = filtered[filtered['Sample_Count'] >= min_samples]

    # Calculate distances
    filtered['Distance_km'] = haversine(cur_lat, cur_lon, filtered['Latitude'], filtered['Longitude'])

    # Get top 5
    nearest = filtered.nsmallest(5, 'Distance_km')

    return [
        dcc.Link(
            html.Div([
                html.H5(f"{row.Location_Name}", style={"marginBottom": "5px"}),
                html.P(f"🆔 {row.Location_ID}", style={"margin": "0"}),
                html.P(f"📏 Distance: {row.Distance_km:.2f} km", style={"margin": "0"}),
                html.P(f"🧪 {row.Test_Type}", style={"margin": "0"}),
                html.P(f"📊 Samples: {row.Sample_Count}", style={"margin": "0"})
            ], style={
                "padding": "12px",
                "marginBottom": "10px",
                "border": "1px solid #ccc",
                "borderRadius": "10px",
                "backgroundColor": "#ffffff",
                "transition": "0.3s",
                "cursor": "pointer",
                "textDecoration": "none",
                "color": "black",
                "boxShadow": "0 2px 6px rgba(0,0,0,0.1)",
                "hover": {
                    "boxShadow": "0 4px 10px rgba(0,0,0,0.2)"
                }
            }),
            href=f"/?id={row.Location_ID}",
            style={"textDecoration": "none"}
        ) for _, row in nearest.iterrows()
    ]
@app.callback(
    Output('time-slider', 'value'),
    Output('time-slider', 'marks'),
    Output('time-slider', 'min'),
    Output('time-slider', 'max'),
    Input('mode-selector', 'value'),
    Input('interval-component', 'n_intervals'),
    State('time-slider', 'value'),
    State('time-slider', 'min'),
    State('time-slider', 'max')
)
def update_slider(mode, n_intervals, current_value, slider_min, slider_max):
    ctx = callback_context

    # Get values list based on mode
    if mode == 'Year':
        values = sorted(df['Year'].dropna().unique())
        marks = {i: {"label": str(v)} for i, v in enumerate(values)}
    else:
        months = sorted(int(v) for v in df['Month'].dropna().unique())
        marks = {i: {"label": calendar.month_abbr[v]} for i, v in enumerate(months)}
        values = months

    min_val = 0
    max_val = len(values) - 1

    if not values:
        # no data case
        return 0, {0: {"label": "No Data"}}, 0, 0

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'mode-selector':
        # Reset slider value when mode changes
        new_value = 0
    elif triggered_id == 'interval-component':
        # Increment slider value on interval tick
        if current_value is None:
            new_value = 0
        else:
            new_value = current_value + 1
            if new_value > max_val:
                new_value = min_val
    else:
        new_value = current_value or 0

    return new_value, marks, min_val, max_val


@callback(
    Output('map', 'figure'),
    Input('time-slider', 'value'),
    Input('mode-selector', 'value'),
    Input('test-type-filter', 'value'),
    Input('parameter-selector', 'value'),
    Input('sample-count-slider', 'value'),
)
def update_map(selected_index, mode, selected_test_types,selected_param,min_sample_count):
    flag_col = f"{selected_param}_flagged"
    col_use = selected_param
    # Filter df based on mode and selected index

    if selected_test_types:
        pattern = '|'.join([fr'\b{t}\b' for t in selected_test_types])
        base_df = df[df['Test_Type'].str.contains(pattern, case=False, na=False, regex=True)]
    else: base_df=df
    
    
    if base_df.empty:
        return go.Figure().update_layout(
            mapbox_style="open-street-map",
            mapbox_center={"lat": 50.5, "lon": -4.5},
            mapbox_zoom=7,
            height=600,
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            annotations=[dict(
                text="No data available for the selected filters.",
                showarrow=False,
                x=0.5,
                y=0.5,
                xref='paper',
                yref='paper',
                font=dict(size=16)
            )]
        )

    if mode == 'Year':
        time_value = 2000 + selected_index  # Fixed year range starting from 2000
        filtered = base_df[(base_df['Year'] == time_value) & (base_df[flag_col] != True)]
    else:
        time_value = selected_index + 1  # Months 1–12
        filtered = base_df[(base_df['Month'] == time_value) & (base_df[flag_col] != True)]
    filtered = filtered[filtered['Sample_Count'] >= min_sample_count]


    # Calculate average temperature per location from filtered data
    if filtered.empty:
        fig = go.Figure()

        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox_center={"lat": 50.5, "lon": -4.5},
            mapbox_zoom=7,
            attribution=None ,
            height=600,
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            annotations=[dict(
                text="No data available for the selected filters.",
                showarrow=False,
                align='center',
                x=0.5,
                y=0.5,
                xref='paper',
                yref='paper',
                font=dict(size=16)
            )]

        )
        return fig

    avg_temp_filtered = filtered.groupby("Location_ID")[col_use].mean().reset_index()


    # Merge with location info
    temp_map = location_info.merge(avg_temp_filtered, on="Location_ID", how="left")
    temp_map= temp_map[temp_map[col_use].notnull()]
    # Compute overall min and max temperature for color scale from ALL unflagged data
    all_unflagged = df[df[flag_col] != True]
    if selected_test_types:
        pattern = '|'.join([fr'\b{t}\b' for t in selected_test_types])
        all_unflagged= all_unflagged[all_unflagged['Test_Type'].str.contains(pattern, case=False, na=False, regex=True)]

    temp_min = all_unflagged[col_use].quantile(0.05)
    temp_max = all_unflagged[col_use].quantile(0.95)

    # Avoid identical values
    if temp_min == temp_max:
        temp_min -= 0.1
        temp_max += 0.1

    tickvals = np.linspace(temp_min, temp_max, 10)
    
    # Format the labels as strings, but the last one with "(and above)"
    
    ticktext = [f"{tickvals[0]:.1f} (and below)"] + \
            [f"{val:.1f}" for val in tickvals[1:-1]] + \
            [f"{tickvals[-1]:.1f} (and above)"]
    if not temp_map.empty:
        fig = px.scatter_map(
            temp_map,
            lat="Latitude",
            lon="Longitude",
            hover_name="Location_Name",
            hover_data={"Test_Type": True, col_use: True},
            color=col_use,
            color_continuous_scale="Plasma",
            range_color=[temp_min, temp_max],  # Fix color scale across all data
            zoom=5,
            height=600,

        )
        fig.update_layout(mapbox_style="open-street-map")
        fig.update_traces(marker=dict(size=15))
        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
        fig.update_layout(coloraxis_colorbar=dict(
        tickvals=tickvals,
        ticktext=ticktext,
        ))
        


        return fig
    else:
        fig = go.Figure()

        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox_center={"lat": 50.5, "lon": -4.5},
            mapbox_zoom=7,
            attribution=None ,
            height=600,
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            annotations=[dict(
                text="No data available for the selected filters.",
                showarrow=False,
                align='center',
                x=0.5,
                y=0.5,
                xref='paper',
                yref='paper',
                font=dict(size=16)
            )]

        )
        return fig



@callback(
    Output('location_map', 'figure'),
    Input('location_test-type-filter', 'value'),

    Input('location_sample-count-slider', 'value'),
    Input('url', 'search'),
)
def update_location_map(selected_test_types,min_sample_count,search):
    params = parse_qs(search.lstrip('?'))
    location_id = params.get('id', [None])[0]
    if location_id is None:
        return ""
    current_point = location_info[location_info['Location_ID'] == location_id]

    # Filter df based on mode and selected index

    if selected_test_types:
        pattern = '|'.join([fr'\b{t}\b' for t in selected_test_types])
        base_df = location_info[location_info['Test_Type'].str.contains(pattern, case=False, na=False, regex=True)]
    else: base_df = location_info
 
    
    base_df = base_df[base_df['Location_ID'] != location_id]
    print(current_point)
    # Current location point
    
    
    if base_df.empty:
        return go.Figure().update_layout(
            mapbox_style="open-street-map",
            mapbox_center={"lat": 50.5, "lon": -4.5},
            mapbox_zoom=7,
            height=600,
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            annotations=[dict(
                text="No data available for the selected filters.",
                showarrow=False,
                x=0.5,
                y=0.5,
                xref='paper',
                yref='paper',
                font=dict(size=16)
            )]
        )

    filtered=base_df
    filtered = filtered[filtered['Sample_Count'] >= min_sample_count]

    


    # Calculate average temperature per location from filtered data
    if filtered.empty:
        fig = go.Figure()

        fig.update_layout(
            mapbox_style="open-street-map",
            mapbox_center={"lat": 50.5, "lon": -4.5},
            mapbox_zoom=7,
            height=600,
            margin={"r": 0, "t": 0, "l": 0, "b": 0},
            annotations=[dict(
                text="No data available for the selected filters.",
                showarrow=False,
                align='center',
                x=0.5,
                y=0.5,
                xref='paper',
                yref='paper',
                font=dict(size=16)
            )],
            

        )
        return fig
    fig = go.Figure()

    fig.add_trace(go.Scattermapbox(
        lat=filtered['Latitude'],
        lon=filtered['Longitude'],
        mode='markers',
        marker=dict(size=15, color='grey'),
        name='Other Locations',
        hoverinfo='text',
        text=filtered['Location_ID']  # <-- correct this
    ))
    fig.add_trace(go.Scattermapbox(
        lat=current_point['Latitude'],
        lon=current_point['Longitude'],
        mode='markers',
        marker=dict(size=25, color='gold'),
        name='Selected Location',
        hoverinfo='text',
        text=current_point['Location_ID']
    ))
    fig.update_layout(
    mapbox=dict(
        style="open-street-map",
        center=dict(
            lat=current_point['Latitude'].values[0],
            lon=current_point['Longitude'].values[0],
        ),
        zoom=7,
       
        
    ),
    

    height=600,
    margin={"r": 0, "t": 0, "l": 0, "b": 0},
    showlegend=False
)
    return fig
    

@callback(
    Output('location-info', 'children'),
    Input('map', 'clickData'),
    Input('time-slider', 'value'),
    Input('mode-selector', 'value'),
    Input('parameter-selector', 'value')
   
)
def display_location_data(clickData, selected_index, mode,selected_param):
    if clickData is None:
        return f'Click on a location to see {selected_param} details.'

    location_name = clickData['points'][0]['hovertext']
    location_id = location_info[location_info['Location_Name'] == location_name]['Location_ID'].values[0]
    

    if mode == 'Year':
        years = sorted(int(v) for v in df['Year'].dropna().unique())
        time_value = years[selected_index]
        filtered = df[(df['Year'] == time_value) & (df['Location_ID'] == location_id)]
        display_time = str(time_value)
    else:
        months = sorted(int(v) for v in df['Month'].dropna().unique())
        time_value = months[selected_index]
        filtered = df[(df['Month'] == time_value) & (df['Location_ID'] == location_id)]
        display_time = calendar.month_abbr[time_value]

    avg_temp = filtered[selected_param].mean()

    return html.Div([
        html.H4(f"{location_name}"),
        html.P(f"{selected_param} ({mode}: {display_time}): {avg_temp:.2f}" if not pd.isna(avg_temp) else "No data available."),
        html.Button(
            "Location Page",
            id="more-info-button",
            n_clicks=0,
            **{"data-location-id": location_id},
            style={
                "backgroundColor": "#2d89ef",
                "color": "white",
                "border": "none",
                "padding": "10px 20px",
                "borderRadius": "5px",
                "cursor": "pointer",
                "fontWeight": "bold",
                "marginTop": "10px"
            }
        )

    ])

if __name__ == '__main__':
    app.run(debug=False)

import io, glob, numpy as np, pandas as pd, streamlit as st, plotly.express as px
import pycountry

st.set_page_config(page_title="PEER Data Portal", layout="wide")

# ── guarantee the dict exists every rerun ──────────────────────────────────
if "store" not in st.session_state or not isinstance(st.session_state.store, dict):
    st.session_state.store = {}

# ── UPLOAD SIDEBAR ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⬆️ Upload dataset(s)")
    files = st.file_uploader(
        "Drop Excel or CSV files (must contain Theme | Country | Region | Income columns)",
        accept_multiple_files=True,
        type=["csv", "xlsx"]
    )
    if st.button("Add to portal") and files:
        for f in files:
            df = pd.read_excel(f) if f.type.endswith("excel") else pd.read_csv(f)
            for col in df:
                if df[col].dropna().isin(["Yes", "No"]).all():
                    df[col] = df[col].map({"Yes": 1, "No": 0})
            for theme in df["Theme"].unique():
                part = df[df["Theme"] == theme].copy()
                st.session_state.store[theme] = (
                    pd.concat([st.session_state.store.get(theme, pd.DataFrame()), part])
                    .reset_index(drop=True)
                )
        st.success("Datasets added!")

# ── MAIN UI ────────────────────────────────────────────────────────────────
st.title("PEER Interactive Data Portal")

if not st.session_state.store:
    st.info("No datasets yet – upload some in the sidebar.")
    st.stop()

theme   = st.selectbox("Theme", sorted(st.session_state.store))
df      = st.session_state.store[theme]

regions = st.multiselect(
    "Region(s)",
    sorted(df["Region"].dropna().unique()),
    default=sorted(df["Region"].dropna().unique())
)
incomes = st.multiselect(
    "Income group(s)",
    sorted(df["Income"].dropna().unique()),
    default=sorted(df["Income"].dropna().unique())
)
countries = st.multiselect(
    "Country(ies)",
    sorted(df[df["Region"].isin(regions)]["Country"].unique()),
    default=[]
)

indicators = [c for c in df.columns if c not in ("Theme", "Country", "Region", "Income")]
sel_inds   = st.multiselect("Indicator(s)", indicators, default=indicators[:1])

stat       = st.radio("Statistic", ["Mean", "Median"])
chart_type = st.selectbox("Chart type",
                          ["Bar", "Line", "Scatter", "Radar", "Funnel", "Map"])

# ── FILTER & DISPLAY TABLE ────────────────────────────────────────────────
mask = df["Region"].isin(regions) & df["Income"].isin(incomes)
if countries:
    mask &= df["Country"].isin(countries)
data = df.loc[mask, ["Country", "Region", "Income"] + sel_inds].copy()

st.subheader("Filtered table")
st.dataframe(data, use_container_width=True)

csv = data.to_csv(index=False).encode()
xls = io.BytesIO(); data.to_excel(xls, index=False); xls.seek(0)
st.download_button("Download CSV",  csv, "peer_filtered.csv",  "text/csv")
st.download_button("Download XLSX", xls, "peer_filtered.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── AGGREGATE IF NEEDED ───────────────────────────────────────────────────
if chart_type in ["Bar", "Radar", "Map", "Funnel"]:
    group_field = "Country" if countries else "Region"
    func        = np.mean if stat == "Mean" else np.median
    plot_df     = data.groupby(group_field)[sel_inds].agg(func).reset_index()
else:
    plot_df     = data.copy()

# ── PLOT ------------------------------------------------------------------
if plot_df.empty:
    st.warning("No data / indicators selected.")
    st.stop()

if chart_type == "Bar":
    fig = px.bar(plot_df, x=plot_df.columns[0], y=sel_inds, barmode="group")
elif chart_type == "Line":
    fig = px.line(plot_df, x=plot_df.columns[0], y=sel_inds)
elif chart_type == "Scatter" and len(sel_inds) >= 2:
    fig = px.scatter(plot_df, x=sel_inds[0], y=sel_inds[1],
                     color="Region", hover_name="Country")
elif chart_type == "Radar" and len(sel_inds) >= 2:
    fig = px.line_polar(plot_df.melt(id_vars=plot_df.columns[0]),
                        r="value", theta="variable", color=plot_df.columns[0],
                        line_close=True)
elif chart_type == "Funnel":
    funnel = plot_df[sel_inds].sum().reset_index()
    funnel.columns = ["Stage", "Value"]
    fig = px.funnel(funnel, x="Value", y="Stage")
elif chart_type == "Map":
    def iso3(name):
        try: return pycountry.countries.lookup(name).alpha_3
        except: return None
    plot_df["iso"] = plot_df[plot_df.columns[0]].apply(iso3)
    fig = px.choropleth(plot_df, locations="iso", color=sel_inds[0],
                        hover_name=plot_df.columns[0], color_continuous_scale="Blues")
else:
    st.info("Select ≥2 indicators for scatter/radar.")
    st.stop()

fig.update_layout(height=550, margin=dict(l=20,r=20,t=40,b=10))
st.subheader(f"{chart_type} – {stat} of selected indicator(s)")
st.plotly_chart(fig, use_container_width=True)


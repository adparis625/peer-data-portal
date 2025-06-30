# peer_portal.py
# this is anna d'addio copyright, please do not reproduce without the right citation


import io, os, glob
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import pycountry
from streamlit_plotly_events import plotly_events

st.set_page_config(page_title="PEER Data Portal", layout="wide")

# ─── 1. Ensure the session‐store exists ─────────────────────────────
if "store" not in st.session_state or not isinstance(st.session_state.store, dict):
    st.session_state.store = {}

# ─── 2. Auto‐load from data/ on first run ───────────────────────────
def autoload():
    patterns = glob.glob("data/*.xlsx") + glob.glob("data/*.csv")
    for path in patterns:
        try:
            df0 = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
        except Exception as e:
            st.warning(f"Could not read {os.path.basename(path)}: {e}")
            continue

        # Recode Yes/No → 1/0
        for col in df0.columns:
            if df0[col].dropna().isin(["Yes", "No"]).all():
                df0[col] = df0[col].map({"Yes": 1, "No": 0})

        # Ensure Theme column
        if "Theme" not in df0.columns:
            df0["Theme"] = os.path.basename(path).rsplit(".", 1)[0]

        # Merge into store by theme
        for raw in df0["Theme"].unique():
            theme = str(raw)
            part = df0[df0["Theme"] == raw].copy()
            st.session_state.store[theme] = pd.concat(
                [st.session_state.store.get(theme, pd.DataFrame()), part],
                ignore_index=True
            )

if not st.session_state.store:
    autoload()

# ─── 3. Sidebar uploader ─────────────────────────────────────────────
with st.sidebar:
    st.header("⬆️ Upload dataset(s)")
    uploads = st.file_uploader(
        "Drop Excel/CSV (needs Theme|Country|Region|Income)",
        accept_multiple_files=True, type=["xlsx", "csv"]
    )
    if st.button("Add to portal") and uploads:
        for f in uploads:
            try:
                df1 = pd.read_excel(f) if f.name.endswith(".xlsx") else pd.read_csv(f)
            except Exception as e:
                st.error(f"Failed to load {f.name}: {e}")
                continue

            # Yes/No → 1/0
            for col in df1.columns:
                if df1[col].dropna().isin(["Yes", "No"]).all():
                    df1[col] = df1[col].map({"Yes": 1, "No": 0})

            if "Theme" not in df1.columns:
                df1["Theme"] = f.name.rsplit(".", 1)[0]

            for raw in df1["Theme"].unique():
                theme = str(raw)
                part = df1[df1["Theme"] == raw].copy()
                st.session_state.store[theme] = pd.concat(
                    [st.session_state.store.get(theme, pd.DataFrame()), part],
                    ignore_index=True
                )
        st.success("Datasets added!")

# ─── 4. Main UI ───────────────────────────────────────────────────────
st.title("PEER Interactive Data Portal")
if not st.session_state.store:
    st.info("No data available. Upload via sidebar or place files in /data.")
    st.stop()

theme = st.selectbox("Theme", sorted(st.session_state.store.keys()))
df    = st.session_state.store[theme]

# ─── 5. Optional filters ───────────────────────────────────────────────
regions   = st.multiselect(
    "Region(s) (optional)", 
    options=sorted(df["Region"].dropna().unique()), default=[]
)
incomes   = st.multiselect(
    "Income group(s) (optional)", 
    options=sorted(df["Income"].dropna().unique()), default=[]
)
countries = st.multiselect(
    "Country(ies) (optional)", 
    options=sorted(df["Country"].unique()), default=[]
)

mask = pd.Series(True, index=df.index)
if regions:
    mask &= df["Region"].isin(regions)
if incomes:
    mask &= df["Income"].isin(incomes)
if countries:
    mask &= df["Country"].isin(countries)
data = df.loc[mask, ["Country","Region","Income"] + [c for c in df.columns 
           if c not in ("Theme","Country","Region","Income")]].copy()

st.subheader("Filtered data")
st.dataframe(data, use_container_width=True)
# ─── 7. Indicator & stat selection ─────────────────────────────────────
ind_cols = [c for c in data.columns if c not in ("Theme","Country","Region","Income")]
sel_inds = st.multiselect("Indicator(s)", ind_cols, default=ind_cols[:1])
stat     = st.radio("Statistic", ["Mean","Median"], horizontal=True)
func     = np.mean if stat=="Mean" else np.median

# ─── 8. Group selection ────────────────────────────────────────────────
group = st.selectbox("Group by", ["None","Country","Region","Income"], index=0)

# ─── 9. CSV/XLSX download ──────────────────────────────────────────────
csv = data.to_csv(index=False).encode()
xls = io.BytesIO(); data.to_excel(xls,index=False); xls.seek(0)
st.download_button("⬇️ Download CSV",  csv, "data.csv","text/csv")
st.download_button("⬇️ Download XLSX", xls, "data.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─── 10. Prepare plotting DataFrame ───────────────────────────────────
# Coerce selected columns to numeric
for c in sel_inds:
    data[c] = pd.to_numeric(data[c], errors="coerce")

# Build plot_df based on chart needs and grouping
chart_type = st.selectbox("Chart type",
    ["Bar","Line","Scatter","Radar","Funnel","Map"]
)
if chart_type in ["Bar","Radar","Funnel","Map"]:
    if group=="None":
        if chart_type!="Map":
            st.warning("Select a Group for this chart type.")
            st.stop()
        # Map will always group by Country if None
        agg_df = data.groupby("Country",as_index=False)[sel_inds].agg(func)
    else:
        agg_df = data.groupby(group,as_index=False)[sel_inds].agg(func)
    plot_df = agg_df
else:
    plot_df = data.copy()

if plot_df.empty or not sel_inds:
    st.warning("No data to plot.")
    st.stop()

# ─── 11. Build & show the chart ────────────────────────────────────────
if chart_type=="Bar":
    fig = px.bar(plot_df, x=(group if group!="None" else sel_inds[0]),
                 y=sel_inds, barmode="group")
elif chart_type=="Line":
    fig = px.line(plot_df, x=(group if group!="None" else sel_inds[0]),
                  y=sel_inds)
elif chart_type=="Scatter" and len(sel_inds)>=2:
    fig = px.scatter(plot_df, x=sel_inds[0], y=sel_inds[1],
                     color=(group if group!="None" else None),
                     hover_name="Country")
elif chart_type=="Radar" and len(sel_inds)>=2:
    long = plot_df.melt(id_vars=(group if group!="None" else sel_inds[0]),
                        value_vars=sel_inds)
    fig = px.line_polar(long, r="value", theta="variable",
                        color=(group if group!="None" else None),
                        line_close=True)
elif chart_type=="Funnel":
    funnel = plot_df[sel_inds].sum().reset_index()
    funnel.columns = ["Stage","Value"]
    fig = px.funnel(funnel, x="Value", y="Stage")
elif chart_type == "Map":
    ind = sel_inds[0]

    # 1) Recode 999→NaN and drop missing
    plot_df[ind] = plot_df[ind].replace(999, np.nan)
    d = plot_df.dropna(subset=[ind])
    if d.empty:
        st.warning("No mappable data for this filter / indicator.")
        st.stop()

    # 2) Choose discrete vs continuous
    uniq = d[ind].dropna().unique()
    if len(uniq) <= 10:
        # Discrete palette
        d["cat"] = d[ind].astype(str)
        fig = px.choropleth(
            d,
            locations="Country",
            locationmode="country names",
            color="cat",
            hover_name="Country",
            color_discrete_sequence=px.colors.qualitative.Safe,
            title=f"{ind} categories by country"
        )
    else:
        # Continuous gradient
        fig = px.choropleth(
            d,
            locations="Country",
            locationmode="country names",
            color=ind,
            hover_name="Country",
            color_continuous_scale="Blues",
            title=f"{stat} of {ind} by country"
        )

    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=550)

else:
    st.info("Select ≥2 indicators for Scatter/Radar.")
    st.stop()

fig.update_layout(margin=dict(l=20,r=20,t=40,b=20), height=550)
st.subheader(f"{chart_type} – {stat}")

st.plotly_chart(fig, use_container_width=True)

# ─── 12. Chart click → snapshot link ───────────────────────────────────
events = plotly_events(fig, click_event=True, hover_event=False)
if events:
    ev = events[0]
    country_clicked = ev.get("location") or ev.get("x") or ev.get("hovertext")
    if country_clicked:
        snap = data.loc[data["Country"]==country_clicked, "SnapshotURL"].dropna()
        if not snap.empty:
            url = snap.iat[0]
            st.markdown(
                f'<a href="{url}" target="_blank">▶️ Open full country profile</a>',
                unsafe_allow_html=True
            )
        else:
            st.info(f"No snapshot available for {country_clicked}.")

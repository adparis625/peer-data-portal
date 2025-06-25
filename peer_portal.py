# peer_portal.py

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
    pats = glob.glob("data/*.xlsx") + glob.glob("data/*.csv")
    for path in pats:
        try:
            df0 = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
        except Exception as e:
            st.warning(f"Could not read {path}: {e}")
            continue

        # Recode Yes/No → 1/0
        for col in df0.columns:
            if df0[col].dropna().isin(["Yes", "No"]).all():
                df0[col] = df0[col].map({"Yes":1,"No":0})

        # Ensure Theme column
        if "Theme" not in df0.columns:
            df0["Theme"] = os.path.basename(path).rsplit(".",1)[0]

        # Merge into store by theme
        for raw in df0["Theme"].unique():
            theme = str(raw)
            part  = df0[df0["Theme"]==raw].copy()
            st.session_state.store[theme] = pd.concat(
                [st.session_state.store.get(theme, pd.DataFrame()), part],
                ignore_index=True
            )

if not st.session_state.store:
    autoload()

# ─── 3. Sidebar uploader ─────────────────────────────────────────────
with st.sidebar:
    st.header("⬆️ Upload dataset(s)")
    ups = st.file_uploader("Drop Excel/CSV (needs Theme|Country|Region|Income)",
                            accept_multiple_files=True, type=["xlsx","csv"])
    if st.button("Add to portal") and ups:
        for f in ups:
            try:
                df1 = pd.read_excel(f) if f.name.endswith(".xlsx") else pd.read_csv(f)
            except Exception as e:
                st.error(f"Failed to load {f.name}: {e}")
                continue

            # Yes/No → 1/0
            for col in df1.columns:
                if df1[col].dropna().isin(["Yes","No"]).all():
                    df1[col] = df1[col].map({"Yes":1,"No":0})

            if "Theme" not in df1.columns:
                df1["Theme"] = f.name.rsplit(".",1)[0]

            for raw in df1["Theme"].unique():
                theme = str(raw)
                part  = df1[df1["Theme"]==raw].copy()
                st.session_state.store[theme] = pd.concat(
                    [st.session_state.store.get(theme, pd.DataFrame()), part],
                    ignore_index=True
                )
        st.success("Datasets added!")

# ─── 4. Main UI ───────────────────────────────────────────────────────
st.title("PEER Interactive Data Portal")
if not st.session_state.store:
    st.info("No data. Upload via sidebar or place files in data/")
    st.stop()

# Theme selector
theme = st.selectbox("Theme", sorted(st.session_state.store.keys()))
df    = st.session_state.store[theme]

# Filters
regions   = st.multiselect("Region(s)", sorted(df["Region"].dropna().unique()),
                            default=sorted(df["Region"].dropna().unique()))
incomes   = st.multiselect("Income group(s)", sorted(df["Income"].dropna().unique()),
                            default=sorted(df["Income"].dropna().unique()))
countries = st.multiselect("Country(ies)",
                   sorted(df[df["Region"].isin(regions)]["Country"].unique()))

# Indicator selection
ind_cols = [c for c in df.columns if c not in ("Theme","Country","Region","Income")]
sel_inds = st.multiselect("Indicator(s)", ind_cols, default=ind_cols[:1])

# Statistic choice → bind func
stat = st.radio("Statistic", ["Mean","Median"], horizontal=True)
func = np.mean if stat=="Mean" else np.median

# Chart type
chart_type = st.selectbox("Chart type",
    ["Bar","Line","Scatter","Radar","Funnel","Map"])

# ─── 5. Filter the DataFrame ───────────────────────────────────────────
mask = df["Region"].isin(regions) & df["Income"].isin(incomes)
if countries:
    mask &= df["Country"].isin(countries)
data = df.loc[mask, ["Country","Region","Income"] + sel_inds].copy()

st.subheader("Filtered table")
table = st.data_editor(
    data, hide_index=False, row_selection="single",
    height=300, use_container_width=True, key="tbl"
)

# Row‐click → show snapshot link
sel = st.session_state.get("tbl",{}).get("selected_rows",[])
if sel:
    idx = sel[0]["_index"] if isinstance(sel[0],dict) else sel[0]
    url = data.iloc[idx].get("SnapshotURL")
    if url:
        st.markdown(f"**Policy snapshot:** [{url}]({url})")

# Download buttons
csv = data.to_csv(index=False).encode()
xlsb= io.BytesIO(); data.to_excel(xlsb,index=False); xlsb.seek(0)
st.download_button("Download CSV", csv, "data.csv","text/csv")
st.download_button("Download XLSX", xlsb,"data.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─── 6. Prepare for plotting ────────────────────────────────────────────
# Convert selected columns to numeric
for c in sel_inds:
    if c in data.columns:
        data[c] = pd.to_numeric(data[c],errors="coerce")

# Keep only numeric indicators
numeric_sel = [c for c in sel_inds if pd.api.types.is_numeric_dtype(data[c])]
if not numeric_sel:
    st.warning("Select at least one numeric indicator.")
    st.stop()

# Let user pick grouping
group = st.selectbox("Group by", ["Country","Region","Income"])
if group not in data.columns:
    st.error(f"No column '{group}' in data.")
    st.stop()

# Aggregate if needed
if chart_type in ["Bar","Radar","Map","Funnel"]:
    plot_df = data.groupby(group,as_index=False)[numeric_sel].agg(func)
else:
    plot_df = data.copy()

# ─── 7. Build the chart ────────────────────────────────────────────────
if plot_df.empty:
    st.warning("No data to plot.")
    st.stop()

if chart_type == "Bar":
    fig = px.bar(plot_df, x=group, y=numeric_sel, barmode="group")
elif chart_type == "Line":
    fig = px.line(plot_df, x=group, y=numeric_sel)
elif chart_type == "Scatter" and len(numeric_sel)>=2:
    fig = px.scatter(plot_df, x=numeric_sel[0], y=numeric_sel[1],
                     color=group, hover_name=group)
elif chart_type == "Radar" and len(numeric_sel)>=2:
    long = plot_df.melt(id_vars=group, value_vars=numeric_sel)
    fig = px.line_polar(long, r="value", theta="variable",
                        color=group,line_close=True)
elif chart_type == "Funnel":
    fun = plot_df[numeric_sel].sum().reset_index()
    fun.columns=["Stage","Value"]
    fig = px.funnel(fun, x="Value", y="Stage")
elif chart_type == "Map":
    ind = numeric_sel[0]
    # treat 999 as nan
    plot_df = plot_df.assign(**{ind: lambda d: d[ind].replace(999, np.nan)})
    # iso lookup
    plot_df["iso"] = plot_df[group].apply(
        lambda n: pycountry.countries.lookup(n).alpha_3 if pd.notna(n) else None
    )
    plot_df = plot_df.dropna(subset=["iso",ind])
    # switch scale
    vals = plot_df[ind].dropna().unique()
    if len(vals)>10:
        fig = px.choropleth(plot_df, locations="iso", color=ind,
                            color_continuous_scale="Blues")
    else:
        plot_df["cat"]=plot_df[ind].astype(str)
        cmap = {v: px.colors.qualitative.Safe[i]
                for i,v in enumerate(sorted(plot_df["cat"].unique()))}
        fig = px.choropleth(plot_df, locations="iso", color="cat",
                            color_discrete_map=cmap)
else:
    st.info("Select at least two indicators for Scatter/Radar.")
    st.stop()

fig.update_layout(margin=dict(l=20,r=20,t=40,b=20),height=550)
st.subheader(f"{chart_type} – {stat}")
st.plotly_chart(fig, use_container_width=True)

# Chart click → snapshot link
events = plotly_events(fig, click_event=True)
if events:
    country = events[0].get("x") or events[0].get("hovertext")
    snap = data.loc[data["Country"]==country,"SnapshotURL"].dropna()
    if not snap.empty:
        st.markdown(f"**Policy snapshot:** [{snap.iat[0]}]({snap.iat[0]})")

# peer_portal.py  ───────────────────────────────────────────────────────────
import io, os, glob
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import pycountry

st.set_page_config(page_title="PEER Data Portal", layout="wide")

# ───────── 1. Make sure the central store exists on every rerun ────────────
if "store" not in st.session_state or not isinstance(st.session_state.store, dict):
    st.session_state.store = {}                 # { "Theme" : DataFrame }

# ───────── 2. Automatic load from ./data once per session ──────────────────
def autoload_from_folder(folder="data"):
    patterns = glob.glob(os.path.join(folder, "*.xlsx")) + \
               glob.glob(os.path.join(folder, "*.csv"))
    for path in patterns:
        try:
            df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
        except Exception as exc:
            st.warning(f"❌ Could not read {os.path.basename(path)}: {exc}")
            continue

        # Yes/No → 1/0
        for col in df.columns:
            if df[col].dropna().isin(["Yes", "No"]).all():
                df[col] = df[col].map({"Yes": 1, "No": 0})

        # Theme column optional – fallback to filename
        if "Theme" not in df.columns:
            df["Theme"] = os.path.basename(path).rsplit(".", 1)[0]

        # merge into store (one DataFrame per theme)
        for theme_raw in df["Theme"].unique():
            theme = str(theme_raw)    # ensure key is str
            part  = df[df["Theme"] == theme_raw].copy()
            st.session_state.store[theme] = (
                pd.concat([st.session_state.store.get(theme, pd.DataFrame()), part])
                .reset_index(drop=True)
            )

# run only once (first page load)
if not st.session_state.store:
    autoload_from_folder()

# ───────── 3. Sidebar uploader – can add more datasets on the fly ──────────
with st.sidebar:
    st.header("⬆️  Upload dataset(s)")
    uploads = st.file_uploader(
        "Drop Excel or CSV (needs Theme | Country | Region | Income columns)",
        accept_multiple_files=True, type=["xlsx", "csv"]
    )
    if st.button("Add to portal") and uploads:
        for f in uploads:
            try:
                df = pd.read_excel(f) if f.name.endswith(".xlsx") else pd.read_csv(f)
            except Exception as exc:
                st.error(f"Could not load {f.name}: {exc}")
                continue

            for col in df.columns:
                if df[col].dropna().isin(["Yes", "No"]).all():
                    df[col] = df[col].map({"Yes": 1, "No": 0})

            if "Theme" not in df.columns:
                df["Theme"] = f.name.rsplit(".", 1)[0]

            for theme_raw in df["Theme"].unique():
                theme = str(theme_raw)
                part  = df[df["Theme"] == theme_raw].copy()
                st.session_state.store[theme] = (
                    pd.concat([st.session_state.store.get(theme, pd.DataFrame()), part])
                    .reset_index(drop=True)
                )
        st.success("Datasets added!")

# ───────── 4. Main interface ───────────────────────────────────────────────
st.title("PEER Interactive Data Portal")

if not st.session_state.store:
    st.info("No datasets yet – upload in the sidebar or place files in /data.")
    st.stop()

themes = sorted(map(str, st.session_state.store.keys()))
theme  = st.selectbox("Theme", themes)
df     = st.session_state.store[theme]

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

indicator_cols = [c for c in df.columns
                  if c not in ("Theme", "Country", "Region", "Income")]
sel_inds = st.multiselect("Indicator(s)", indicator_cols,
                          default=indicator_cols[:1])

stat       = st.radio("Statistic", ["Mean", "Median"], horizontal=True)
chart_type = st.selectbox("Chart type",
                          ["Bar", "Line", "Scatter", "Radar", "Funnel", "Map"])

# ───────── 5. Filter dataset ───────────────────────────────────────────────
mask = df["Region"].isin(regions) & df["Income"].isin(incomes)
if countries:
    mask &= df["Country"].isin(countries)
data = df.loc[mask, ["Country", "Region", "Income"] + sel_inds].copy()

st.subheader("Filtered table")
st.dataframe(data, use_container_width=True)
row_clicked = st.dataframe(data, use_container_width=True).selected_rows
if row_clicked:
    url = row_clicked[0].get("SnapshotURL")
    if url:
        st.markdown(f"**Policy snapshot:** [{url}]({url})", unsafe_allow_html=True)


# download buttons
csv = data.to_csv(index=False).encode()
xls = io.BytesIO(); data.to_excel(xls, index=False); xls.seek(0)
st.download_button("⬇️ CSV", csv, "peer_filtered.csv", "text/csv", key="csv_dl")
st.download_button("⬇️ XLSX", xls, "peer_filtered.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   key="xlsx_dl")

# ───────── 6. Prepare data for plotting ────────────────────────────────────
if chart_type in ["Bar", "Radar", "Map", "Funnel"]:
    group = "Country" if countries else "Region"
    func  = np.mean if stat == "Mean" else np.median
    plot_df = data.groupby(group)[sel_inds].agg(func).reset_index()
else:
    plot_df = data.copy()

if plot_df.empty or not sel_inds:
    st.warning("No data/indicators selected.")
    st.stop()

# ───────── 7. Build chart with Plotly ──────────────────────────────────────
if chart_type == "Bar":
    fig = px.bar(plot_df, x=plot_df.columns[0], y=sel_inds, barmode="group")
elif chart_type == "Line":
    fig = px.line(plot_df, x=plot_df.columns[0], y=sel_inds)
elif chart_type == "Scatter" and len(sel_inds) >= 2:
    fig = px.scatter(plot_df, x=sel_inds[0], y=sel_inds[1],
                     color="Region", hover_name="Country")
elif chart_type == "Radar" and len(sel_inds) >= 2:
    fig = px.line_polar(plot_df.melt(id_vars=plot_df.columns[0]),
                        r="value", theta="variable",
                        color=plot_df.columns[0], line_close=True)
elif chart_type == "Funnel":
    funnel = plot_df[sel_inds].sum().reset_index()
    funnel.columns = ["Stage", "Value"]
    fig = px.funnel(funnel, x="Value", y="Stage")
elif chart_type == "Map":
    def iso3(name):
        try:
            return pycountry.countries.lookup(name).alpha_3
        except Exception:
            return None
    plot_df["iso"] = plot_df[plot_df.columns[0]].apply(iso3)
    fig = px.choropleth(plot_df, locations="iso", color=sel_inds[0],
                        hover_name=plot_df.columns[0],
                        color_continuous_scale="Blues")
else:
    st.info("Select ≥2 indicators for Scatter/Radar.")
    st.stop()

fig.update_layout(height=560, margin=dict(l=20, r=20, t=40, b=10))
st.subheader(f"{chart_type} – {stat}")
st.plotly_chart(fig, use_container_width=True)

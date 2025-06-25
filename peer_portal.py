import io, glob, os, numpy as np, pandas as pd, streamlit as st, plotly.express as px
# import plotly.graph_objects as go
import pycountry

##############################################################################
# 1) SESSION STATE: store uploaded datasets across app interactions
##############################################################################
     # {Theme -> DataFrame}
 
if "store" not in st.session_state or not isinstance(st.session_state.store, dict):
    st.session_state.store = {} 


# ────────────────────────────────────────────────────────────────
# 2. OPTIONAL: auto-load every .xlsx / .csv in a data/ folder ONCE
# ────────────────────────────────────────────────────────────────
def autoload_from_folder(folder="data"):
    for path in glob.glob(os.path.join(folder, "*.xlsx")) + \
               glob.glob(os.path.join(folder, "*.csv")):
        try:
            df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
        except Exception as e:
            st.warning(f"Could not read {os.path.basename(path)}: {e}")
            continue
        # recode Yes/No → 1/0
        for col in df:
            if df[col].dropna().isin(["Yes", "No"]).all():
                df[col] = df[col].map({"Yes": 1, "No": 0})

        if "Theme" not in df.columns:
            df["Theme"] = os.path.basename(path).rsplit(".", 1)[0]

        # merge into the store
        for theme in df["Theme"].unique():
            part = df[df["Theme"] == theme].copy()
            st.session_state.store[theme] = (
                pd.concat([st.session_state.store.get(theme, pd.DataFrame()), part])
                .reset_index(drop=True)
            )

# run only the first time
if not st.session_state.store:
    autoload_from_folder()

# ────────────────────────────────────────────────────────────────
# 3. From here on you can safely build the UI
# ────────────────────────────────────────────────────────────────
st.title("PEER Interactive Data Portal")

if not st.session_state.store:
    st.info("No datasets yet – use the sidebar uploader.")
    st.stop()

themes = sorted(st.session_state.store.keys())   # ← now guaranteed to work
theme  = st.selectbox("Theme", themes)
df     = st.session_state.store[theme]

# … keep the rest of your code (region / income / country selectors,
#    chart drawing, export buttons, etc.) …

st.set_page_config(page_title="PEER Data Portal", layout="wide")

##############################################################################
# 2) UPLOAD AREA (left sidebar, visible to all)
##############################################################################
with st.sidebar:
    st.header("⬆️ Upload dataset(s)")
    files = st.file_uploader(
        "Drop Excel or CSV files (must contain Theme | Country | Region columns)",
        accept_multiple_files=True,
        type=["csv", "xlsx"]
    )
    if st.button("Add to portal") and files:
        for f in files:
            # read file
            if f.type == "text/csv":
                df = pd.read_csv(f)
            else:
                df = pd.read_excel(f)
            # recode Yes/No
            for col in df.columns:
                if df[col].dropna().isin(["Yes", "No"]).all():
                    df[col] = df[col].map({"Yes": 1, "No": 0})
            # append to store by Theme value(s)
            for theme in df["Theme"].unique():
                part = df[df["Theme"] == theme].copy()
                st.session_state.store[theme] = (
                    pd.concat([st.session_state.store.get(theme, pd.DataFrame()), part])
                    .reset_index(drop=True)
                )
        st.success("Datasets added! Switch to *Explore* ▶")

##############################################################################
# 3) UI – choose dataset & filters
##############################################################################
st.title("PEER Interactive Data Portal")

if not st.session_state.store:
    st.info("No datasets yet – upload some in the sidebar.")
    st.stop()

themes = sorted(st.session_state.store.keys())
theme = st.selectbox("Theme", themes)

df = st.session_state.store[theme]

regions = st.multiselect("Region(s)", sorted(df["Region"].unique()),
                         default=sorted(df["Region"].unique()))
countries = st.multiselect("Country(ies)",
                           sorted(df[df["Region"].isin(regions)]["Country"].unique()),
                           default=[])

indicators = [c for c in df.columns if c not in ["Theme", "Country", "Region"]]
sel_inds = st.multiselect("Indicator(s)", indicators, default=indicators[:1])

stat = st.radio("Statistic", ["Mean", "Median"])
chart_type = st.selectbox(
    "Chart type",
    ["Bar", "Line", "Scatter", "Radar", "Funnel", "Map"]
)

##############################################################################
# 4) FILTER DATAFRAME
##############################################################################
mask = df["Region"].isin(regions)
if countries:
    mask &= df["Country"].isin(countries)
data = df.loc[mask, ["Country", "Region"] + sel_inds].copy()

if data.empty:
    st.warning("No rows match your filters.")
    st.stop()

##############################################################################
# 5) AGGREGATE (if needed)
##############################################################################
if chart_type in ["Bar", "Radar", "Map", "Funnel"]:
    group_field = "Region" if not countries else "Country"
    agg_fun = np.mean if stat == "Mean" else np.median
    plot_df = data.groupby(group_field)[sel_inds].agg(agg_fun).reset_index()
else:
    plot_df = data.copy()    # scatter / line use raw or grouped by country-year

##############################################################################
# 6) DISPLAY TABLE + DOWNLOAD
##############################################################################
st.subheader("Filtered table")
st.dataframe(data, use_container_width=True)

csv = data.to_csv(index=False).encode()
xls = io.BytesIO(); data.to_excel(xls, index=False); xls.seek(0)
st.download_button("Download CSV", csv, "peer_filtered.csv", "text/csv")
st.download_button("Download XLSX", xls, "peer_filtered.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

##############################################################################
# 7) DRAW CHART
##############################################################################
st.subheader(f"{chart_type} chart  – {stat} of selected indicator(s)")

if chart_type == "Bar":
    fig = px.bar(plot_df, x=plot_df.columns[0], y=sel_inds, barmode="group")
elif chart_type == "Line":
    fig = px.line(plot_df, x="Country", y=sel_inds) if len(sel_inds)<=3 else \
          px.line(plot_df.melt(id_vars="Country"), x="Country", y="value", color="variable")
elif chart_type == "Scatter" and len(sel_inds) >= 2:
    fig = px.scatter(plot_df, x=sel_inds[0], y=sel_inds[1],
                     color="Region", hover_name="Country")
elif chart_type == "Radar":
    if len(sel_inds) == 1:
        st.info("Select ≥2 indicators for a radar.")
        st.stop()
    long = plot_df.melt(id_vars=plot_df.columns[0])
    fig = px.line_polar(long, r="value", theta="variable",
                        color=plot_df.columns[0], line_close=True)
elif chart_type == "Funnel":
    if len(sel_inds) < 1:
        st.stop()
    fun = plot_df[sel_inds].sum().reset_index()
    fun.columns = ["Stage", "Value"]
    fig = px.funnel(fun, x="Value", y="Stage")
elif chart_type == "Map":
    # convert country → ISO-3 for Plotly
    def iso3(name):
        try: return pycountry.countries.lookup(name).alpha_3
        except: return None
    plot_df["iso"] = plot_df[plot_df.columns[0]].apply(iso3)
    first_ind = sel_inds[0]
    fig = px.choropleth(plot_df, locations="iso", color=first_ind,
                        hover_name=plot_df.columns[0],
                        color_continuous_scale="Blues")
else:
    st.info("Choose at least two indicators for scatter / adjust selections.")
    st.stop()

fig.update_layout(height=550, margin=dict(l=20,r=20,t=40,b=10))
st.plotly_chart(fig, use_container_width=True)

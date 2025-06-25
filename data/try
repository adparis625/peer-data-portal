for f in files:
    try:
        if f.name.endswith(".csv"):
            df = pd.read_csv(f)
        else:
            df = pd.read_excel(f)          # needs openpyxl in requirements.txt
    except Exception as e:
        st.error(f"❌ Could not load {f.name}: {e}")
        continue            # skip to next file
  
    # if we reach here df exists → safe to iterate
    if "Theme" not in df.columns:
        st.warning(f"'Theme' column missing in {f.name}. Using filename instead.")
        df["Theme"] = f.name.rsplit(".", 1)[0]

    for theme in df["Theme"].unique():
        part = df[df["Theme"] == theme].copy()
        st.session_state.store[theme] = (
            pd.concat([st.session_state.store.get(theme, pd.DataFrame()), part])
            .reset_index(drop=True)
        )

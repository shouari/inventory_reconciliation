import streamlit as st
import pandas as pd
from Levenshtein import ratio
import numpy as np

st.set_page_config(page_title="📦 Outil de Réconciliation des Stocks", page_icon=":package:", layout="wide")



# Step 1: File Upload
st.sidebar.header("Étape 1: Importer les fichiers")
qb_file = st.sidebar.file_uploader("📘 Importer l'inventaire QuickBooks", type=["csv", "xlsx"])
dt_file = st.sidebar.file_uploader("📗 Importer l'inventaire D-Tools", type=["csv", "xlsx"])

if qb_file and dt_file:
    # Load Data (Ensure SKU is string to avoid ArrowTypeError)
    df_qb = pd.read_csv(qb_file, sep=";", dtype=str) if qb_file.name.endswith('.csv') else pd.read_excel(qb_file, dtype=str)
    df_dt = pd.read_csv(dt_file, sep=";", dtype=str) if dt_file.name.endswith('.csv') else pd.read_excel(dt_file, dtype=str)

    # Normalize SKUs
    df_qb["SKU"] = df_qb["SKU"].astype(str).str.strip().str.upper()
    df_dt["SKU"] = df_dt["SKU"].astype(str).str.strip().str.upper()

    # Sidebar Navigation
    if "step" not in st.session_state:
        st.session_state["step"] = 1

    step = st.session_state["step"]

# Function for pagination
def paginate_dataframe(df, page_size=100):
    total_pages = np.ceil(len(df) / page_size).astype(int)
    page_number = st.session_state.get("page_number", 1)

    if page_number > total_pages:
        page_number = 1  # Reset if out of range

    start_idx = (page_number - 1) * page_size
    end_idx = start_idx + page_size
    df_page = df.iloc[start_idx:end_idx]

    # Pagination controls
    col1, col2, col3 = st.columns([1, 4, 1])
    if col1.button("⬅️ Précédent") and page_number > 1:
        st.session_state["page_number"] = page_number - 1
        st.rerun()

    col3.write(f"📄 Page {page_number} / {total_pages}")

    if col3.button("➡️ Suivant") and page_number < total_pages:
        st.session_state["page_number"] = page_number + 1
        st.rerun()

    return df_page

    # ------------------------- STEP 1: CLEAN INDIVIDUAL FILES -------------------------
if step == 1:
    st.header("🔍 Étape 1: Nettoyage des fichiers individuels")

    col1, col2 = st.columns(2)

    def process_duplicates(df, source_name):
        """Find duplicates within the same file and allow bulk resolution via table."""
        st.subheader(f"🛠️ Gestion des doublons - {source_name}")
        dupes = df[df.duplicated(subset=['SKU'], keep=False)].copy()

        if not dupes.empty:
            st.write(f"⚠️ {len(dupes)} doublons détectés.")

            # Add selection column
            dupes["Sélectionner"] = False

            # Paginate table
            dupes_page = paginate_dataframe(dupes)

            # Display paginated table with checkboxes
            edited_df = st.data_editor(dupes_page, column_config={"Sélectionner": st.column_config.CheckboxColumn()}, hide_index=True)

            # Bulk actions
            col1, col2 = st.columns(2)
            if col1.button("🟡 Fusionner les sélectionnés"):
                selected_skus = edited_df[edited_df["Sélectionner"] == True]["SKU"].unique()
                df = df[~df["SKU"].isin(selected_skus)]  # Remove duplicates
                df = pd.concat([df, dupes[dupes["SKU"].isin(selected_skus)].drop(columns=["Sélectionner"])], ignore_index=True)
                st.success(f"✅ {len(selected_skus)} SKUs fusionnés !")
                st.rerun()

            if col2.button("🔴 Supprimer les sélectionnés"):
                selected_skus = edited_df[edited_df["Sélectionner"] == True]["SKU"].unique()
                df = df[~df["SKU"].isin(selected_skus)]
                st.success(f"✅ {len(selected_skus)} SKUs supprimés !")
                st.rerun()

            return df
        else:
            st.success(f"Aucun doublon trouvé dans {source_name}.")
            return df

    # Process duplicates for both QuickBooks & D-Tools
    with col1:
        st.markdown("### 📘 Inventaire QuickBooks")
        st.metric("📦 Total Articles", len(df_qb))
        df_qb = process_duplicates(df_qb, "QuickBooks")

    with col2:
        st.markdown("### 📗 Inventaire D-Tools")
        st.metric("📦 Total Articles", len(df_dt))
        df_dt = process_duplicates(df_dt, "D-Tools")

    # Move to next step
    if st.button("🔜 Passer à l'étape 2"):
        st.session_state["df_qb_cleaned"] = df_qb
        st.session_state["df_dt_cleaned"] = df_dt
        st.session_state["step"] = 2
        st.rerun()


    # ------------------------- STEP 2: MATCH SKUs -------------------------
    if step == 2:
        st.header("🔍 Étape 2: Correspondance des SKUs entre QuickBooks & D-Tools")

        df_qb = st.session_state.get("df_qb_cleaned", pd.DataFrame())
        df_dt = st.session_state.get("df_dt_cleaned", pd.DataFrame())

        if not df_qb.empty and not df_dt.empty:
            # --- Handle Unmatched SKUs ---
            st.subheader("❌ SKUs Sans Correspondance")
            non_matching_qb = df_qb[~df_qb["SKU"].isin(df_dt["SKU"])]
            non_matching_dt = df_dt[~df_dt["SKU"].isin(df_qb["SKU"])]

            if not non_matching_qb.empty:
                non_matching_qb["Sélectionner"] = False
                st.write("📘 SKUs dans QuickBooks mais absents de D-Tools")
                edited_qb = st.data_editor(non_matching_qb, column_config={"Sélectionner": st.column_config.CheckboxColumn()}, hide_index=True)

                if st.button("🟡 Garder sélectionnés dans QuickBooks"):
                    selected_skus = edited_qb[edited_qb["Sélectionner"] == True]["SKU"].unique()
                    df_qb = df_qb[df_qb["SKU"].isin(selected_skus)]
                    st.success(f"✅ {len(selected_skus)} SKUs conservés.")
                    st.rerun()

            if not non_matching_dt.empty:
                non_matching_dt["Sélectionner"] = False
                st.write("📗 SKUs dans D-Tools mais absents de QuickBooks")
                edited_dt = st.data_editor(non_matching_dt, column_config={"Sélectionner": st.column_config.CheckboxColumn()}, hide_index=True)

                if st.button("🟡 Garder sélectionnés dans D-Tools"):
                    selected_skus = edited_dt[edited_dt["Sélectionner"] == True]["SKU"].unique()
                    df_dt = df_dt[df_dt["SKU"].isin(selected_skus)]
                    st.success(f"✅ {len(selected_skus)} SKUs conservés.")
                    st.rerun()

            # --- Fuzzy Matching with Bulk Confirmation ---
            st.subheader("⚠️ Correspondances Approximatives (Fuzzy Matching)")
            fuzzy_matches = get_fuzzy_matches(df_qb["SKU"].unique(), df_dt["SKU"].unique())

            if not fuzzy_matches.empty:
                fuzzy_matches["Sélectionner"] = False
                st.data_editor(fuzzy_matches, column_config={"Sélectionner": st.column_config.CheckboxColumn()}, hide_index=True)

                if st.button("🟢 Confirmer les correspondances sélectionnées"):
                    selected_matches = fuzzy_matches[fuzzy_matches["Sélectionner"] == True]
                    for _, row in selected_matches.iterrows():
                        df_qb = df_qb[df_qb["SKU"] != row["SKU QuickBooks"]]
                        df_dt = df_dt[df_dt["SKU"] != row["SKU D-Tools"]]
                    st.success(f"✅ {len(selected_matches)} correspondances confirmées.")
                    st.rerun()

            if st.button("🔜 Passer à l'étape 3"):
                st.session_state["df_final"] = pd.concat([df_qb, df_dt], ignore_index=True)
                st.session_state["step"] = 3
                st.rerun()


    # ------------------------- STEP 3: FINALIZE & EXPORT -------------------------
    if step == 3:
        st.header("📤 Étape 3: Finalisation & Export")

        df_final = st.session_state.get("df_final", pd.DataFrame())

        if not df_final.empty:
            st.subheader("📜 Inventaire final réconcilié")
            st.dataframe(df_final)

            st.download_button(
                label="📥 Télécharger l'inventaire nettoyé",
                data=df_final.to_csv(index=False).encode("utf-8"),
                file_name="inventaire_nettoye.csv",
                mime="text/csv"
            )

        if st.button("🔙 Retour au début"):
            st.session_state["step"] = 1
            st.rerun()

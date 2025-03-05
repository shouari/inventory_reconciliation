import streamlit as st
import pandas as pd
from Levenshtein import ratio
import itertools
import io
from xlsxwriter import Workbook

def normalize_sku(sku):
    """" Normalize SKU by removing spaces and converting to lowercase """
    return ''.join(filter(str.isalnum, sku.upper()))

st.set_page_config(layout="wide")

st.title("📦 Outil de Réconciliation des Stocks ")


# ---- File Upload ----
st.sidebar.header("Étape 1: Importer les fichiers")
qb_file = st.sidebar.file_uploader("📘 Inventaire QuickBooks", type=["csv", "xlsx"])
dt_file = st.sidebar.file_uploader("📗 Inventaire D-Tools", type=["csv", "xlsx"])

if qb_file and dt_file:
    # Load Data (Ensure SKU is string)
    df_qb = pd.read_csv(qb_file, sep=";", dtype=str) if qb_file.name.endswith('.csv') else pd.read_excel(qb_file, dtype=str)
    df_dt = pd.read_csv(dt_file, sep=";", dtype=str) if dt_file.name.endswith('.csv') else pd.read_excel(dt_file, dtype=str)

    # Normalize SKUs
    df_qb["SKU_NORM"] = df_qb["SKU"].astype(str).str.strip().str.upper().apply(normalize_sku)
    df_dt["SKU_NORM"] = df_dt["SKU"]. astype(str).str.strip().str.upper().apply(normalize_sku)

    # Step Navigation
    if "step" not in st.session_state:
        st.session_state["step"] = 1 
    step = st.session_state["step"]

    # ------------------------- STEP 1: CLEAN INDIVIDUAL FILES -------------------------
    if step == 1:
        st.header("🔍 Étape 1: Nettoyage des fichiers individuels")

        # ✅ Detect Exact Duplicates (More Efficient)
        duplicate_skus_qb = df_qb[df_qb.duplicated("SKU_NORM", keep=False)]["SKU_NORM"].unique()
        duplicate_skus_dt = df_dt[df_dt.duplicated("SKU_NORM", keep=False)]["SKU_NORM"].unique()

        # ✅ Save Exact Duplicates in Session State
        if "qb_duplicate_queue" not in st.session_state:
            st.session_state["qb_duplicate_queue"] = list(duplicate_skus_qb)
            st.session_state["qb_cleaned_data"] = df_qb.copy()

        if "dt_duplicate_queue" not in st.session_state:
            st.session_state["dt_duplicate_queue"] = list(duplicate_skus_dt)
            st.session_state["dt_cleaned_data"] = df_dt.copy()

        # ✅ Optimized Fuzzy Matching (Using itertools)
        if "qb_fuzzy_duplicates" not in st.session_state:
            fuzzy_qb_duplicates = [
                (sku1, sku2) for sku1, sku2 in itertools.combinations(df_qb["SKU_NORM"].unique(), 2)
                if ratio(sku1, sku2) > 0.95
            ]
            st.session_state["qb_fuzzy_duplicates"] = fuzzy_qb_duplicates

        if "dt_fuzzy_duplicates" not in st.session_state:
            fuzzy_dt_duplicates = [
                (sku1, sku2) for sku1, sku2 in itertools.combinations(df_dt["SKU_NORM"].unique(), 2)
                if ratio(sku1, sku2) > 0.95
            ]
            st.session_state["dt_fuzzy_duplicates"] = fuzzy_dt_duplicates

        # ✅ Display Duplicate Counts
        total_duplicates_qb = len(st.session_state["qb_duplicate_queue"])
        total_duplicates_dt = len(st.session_state["dt_duplicate_queue"])
        total_fuzzy_qb = len(st.session_state["qb_fuzzy_duplicates"])
        total_fuzzy_dt = len(st.session_state["dt_fuzzy_duplicates"])

        st.subheader(f"📊 Nombre total de doublons détectés:")
        st.write(f"📘 QuickBooks: {total_duplicates_qb} exacts, {total_fuzzy_qb} approximatifs")
        st.write(f"📗 D-Tools: {total_duplicates_dt} exacts, {total_fuzzy_dt} approximatifs")

        if st.button("⏭️ Ignorer le nettoyage et passer à l'étape 2"):
            st.session_state["step"] = 2
            st.rerun()

        # ✅ Process Exact & Fuzzy Duplicates
        if len(st.session_state["qb_duplicate_queue"]) > 0:
            current_sku = st.session_state["qb_duplicate_queue"][0]
            df_duplicate_group_qb = st.session_state["qb_cleaned_data"][st.session_state["qb_cleaned_data"]["SKU_NORM"] == current_sku]

            st.subheader(f"🛠️ Gestion des doublons (QuickBooks) - SKU: `{current_sku}`")
            st.dataframe(df_duplicate_group_qb)

            action = st.radio("Choisissez une action:", ["✅ Garder", "🟡 Fusionner", "🔴 Supprimer"], key="qb_action_choice")

            if st.button("Suivant ➡️", key="qb_next"):
                st.session_state["qb_duplicate_queue"].pop(0)
                st.rerun()

        elif len(st.session_state["qb_fuzzy_duplicates"]) > 0:
            fuzzy_sku1, fuzzy_sku2 = st.session_state["qb_fuzzy_duplicates"][0]

            st.subheader(f"🔍 Correspondance Approximative (QuickBooks)")
            st.write(f"❓ Confirmer `{fuzzy_sku1}` ≈ `{fuzzy_sku2}` comme duplicatas?")
            confirm = st.radio(f"Fusionner `{fuzzy_sku1}` et `{fuzzy_sku2}` ?", ["❌ Non", "✅ Oui"], key=f"qb_fuzzy_{fuzzy_sku1}_{fuzzy_sku2}")

            if st.button("Suivant ➡️", key=f"qb_fuzzy_next_{fuzzy_sku1}"):
                st.session_state["qb_fuzzy_duplicates"].pop(0)
                st.rerun()

        else:
            st.success("✅ Tous les doublons (exacts et approximatifs) ont été traités !")

            df_final_qb = st.session_state["qb_cleaned_data"]
            df_final_dt = st.session_state["dt_cleaned_data"]

            cleaned_csv_qb = df_final_qb.to_csv(index=False).encode("utf-8")
            cleaned_csv_dt = df_final_dt.to_csv(index=False).encode("utf-8")

            col1, col2 = st.columns(2)
            with col1:
                st.download_button("📥 Télécharger Inventaire QuickBooks", data=cleaned_csv_qb, file_name="quickbooks_nettoye.csv", mime="text/csv")
            with col2:
                st.download_button("📥 Télécharger Inventaire D-Tools", data=cleaned_csv_dt, file_name="dtools_nettoye.csv", mime="text/csv")

            if st.button("🔜 Passer à l'étape 2"):
                st.session_state["step"] = 2
                st.rerun()


# ------------------------- STEP 2: MATCH SKUs (Step-by-Step) -------------------------
    if step == 2:
        st.header("🔍 Étape 2: Correspondance des SKUs")

        df_qb = st.session_state["qb_cleaned_data"]
        df_dt = st.session_state["dt_cleaned_data"]

        # ---- Exact Matches ----
        exact_matches = df_qb[df_qb["SKU"].isin(df_dt["SKU"])].copy()
        exact_matches["Match Type"] = "Exact"
        st.session_state["exact_matches"] = exact_matches

        with st.expander(f"✅ {len(exact_matches)} Correspondances Exactes (Afficher / Masquer)"):
            st.dataframe(exact_matches)

        # ---- Mismatches ----
        mismatched_qb = df_qb[~df_qb["SKU"].isin(df_dt["SKU"])].copy()
        mismatched_dt = df_dt[~df_dt["SKU"].isin(df_qb["SKU"])].copy()
        total_mismatches = len(mismatched_qb) + len(mismatched_dt)

        st.session_state["mismatched_qb"] = mismatched_qb
        st.session_state["mismatched_dt"] = mismatched_dt

        st.subheader(f"🔍 Nombre total de SKU non correspondants : {total_mismatches}")

        col1, col2 = st.columns(2)
        with col1:
            st.write(f"📘 QuickBooks SKUs non trouvés dans D-Tools: {len(mismatched_qb)}")
            st.dataframe(mismatched_qb)
        with col2:
            st.write(f"📗 D-Tools SKUs non trouvés dans QuickBooks: {len(mismatched_dt)}")
            st.dataframe(mismatched_dt)

        # ---- Fuzzy Matches ----
        if "fuzzy_queue" not in st.session_state or not st.session_state["fuzzy_queue"]:
            fuzzy_matches = [
                {"QuickBooks SKU": qb_sku, "D-Tools SKU": dt_sku, "Similitude": round(ratio(qb_sku, dt_sku) * 100, 2)}
                for qb_sku in mismatched_qb["SKU"]
                for dt_sku in mismatched_dt["SKU"]
                if 90 < ratio(qb_sku, dt_sku) * 100 < 100 and qb_sku != dt_sku
            ]
            fuzzy_matches_df = pd.DataFrame(fuzzy_matches).sort_values(by="Similitude", ascending=False)
            st.session_state["fuzzy_queue"] = fuzzy_matches_df.to_dict(orient="records")

        st.subheader(f"⚠️ {len(st.session_state['fuzzy_queue'])} Correspondances Approximatives")

        if len(st.session_state["fuzzy_queue"]) > 0:
            fuzzy_match = st.session_state["fuzzy_queue"][0]
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write("📘 **QuickBooks SKU**")
                st.write(f"🔵 `{fuzzy_match['QuickBooks SKU']}`")
            with col2:
                st.write("📗 **D-Tools SKU**")
                st.write(f"🟢 `{fuzzy_match['D-Tools SKU']}`")
            with col3:
                st.write("📊 **Similitude**")
                similarity = fuzzy_match['Similitude']
                color = f"background-color: rgba({255 - int(similarity * 2.55)}, {int(similarity * 2.55)}, 0, 0.5); padding:5px; border-radius:8px;"
                st.markdown(f"<div style='{color}'>{similarity:.0f}%</div>", unsafe_allow_html=True)

            action = st.radio("Choisissez une action:", ["✅ Garder les deux", "🟡 Fusionner", "🔴 Ignorer"], key="fuzzy_action")

            if st.button("Suivant ➡️"):
                if action == "🟡 Fusionner":
                    df_dt = df_dt[df_dt["SKU"] != fuzzy_match["D-Tools SKU"]]
                    st.session_state["fuzzy_selected"] = st.session_state.get("fuzzy_selected", []) + [fuzzy_match]
                elif action == "✅ Garder les deux":
                    pass  # Keep both
                st.session_state["fuzzy_queue"].pop(0)
                st.session_state["dt_cleaned_data"] = df_dt
                st.rerun()
            
        if st.button("🔜 Passer à l'étape 3", key="step_3"):
            st.session_state["step"] = 3
            st.rerun()

   # ------------------------- STEP 3: FINALIZE & EXPORT -------------------------
    if step == 3:
        st.header("📤 Étape 3: Finalisation & Export")

        if st.button("🔙 Retour à l'étape 2"):
            st.session_state["step"] = 2
            st.rerun()

        # ✅ Start with the D-Tools dataset to preserve template
        df_output = st.session_state["dt_cleaned_data"].copy()

        # ✅ Identify QuickBooks "Quantité en stock" column dynamically
        qb_qty_col = next((col for col in df_qb.columns if "quantité en stock" in col.lower()), None)

        if qb_qty_col:
            df_qb.rename(columns={qb_qty_col: "Quantity on Hand"}, inplace=True)
        else:
            st.warning("⚠️ 'Quantité en stock' column not found in QuickBooks data. Proceeding without it.")

        # ✅ Merge QuickBooks Quantities into D-Tools Dataset
        if "Quantity on Hand" in df_qb.columns:
            df_output = df_output.merge(df_qb[["SKU", "Quantity on Hand"]], on="SKU", how="left", suffixes=("", "_QB"))

            # ✅ Ensure "Quantity on Hand" is correctly assigned
            df_output["Quantity on Hand"] = df_output["Quantity on Hand_QB"].combine_first(df_output["Quantity on Hand"])

            # ✅ Remove the extra column
            df_output.drop(columns=["Quantity on Hand_QB"], inplace=True)
        
        # ✅ Extract & Prepare Fuzzy Matches Data
        df_fuzzy_selected = pd.DataFrame(st.session_state.get("fuzzy_selected", []))

        if not df_fuzzy_selected.empty:
            df_fuzzy_selected = df_fuzzy_selected.rename(columns={"QuickBooks SKU": "SKU"})  # Align SKU column
            df_fuzzy_selected["Match Type"] = "Fuzzy Merged"

        # ✅ Prepare Exact Matches Data
        exact_matches = st.session_state.get("exact_matches", pd.DataFrame()).copy()
        
        if not exact_matches.empty:
            exact_matches["Match Type"] = "Exact Match"
            exact_matches = exact_matches.rename(columns={"QuickBooks SKU": "SKU"})  # Align SKU column

        # ✅ Merge Exact Matches and Fuzzy Matches into the D-Tools Format
        final_output = df_output.copy()
       
        for df_merge in [exact_matches, df_fuzzy_selected]:
            if not df_merge.empty and "Quantity on Hand" in df_merge.columns:
                final_output = final_output.merge(
                    df_merge[["SKU", "Quantity on Hand"]], on="SKU", how="left", suffixes=("", "_Match")
                )
         # ✅ Ensure No Duplicate "Quantity on Hand" Columns
        if "Quantity on Hand_QB" in final_output.columns and "Quantity on Hand_Match" in final_output.columns:
            final_output["Quantity on Hand"] = final_output["Quantity on Hand_QB"].combine_first(final_output["Quantity on Hand_Match"])
            final_output.drop(columns=["Quantity on Hand_QB", "Quantity on Hand_Match"], inplace=True)
        elif "Quantity on Hand_QB" in final_output.columns:
            final_output.rename(columns={"Quantity on Hand_QB": "Quantity on Hand"}, inplace=True)
        elif "Quantity on Hand_Match" in final_output.columns:
            final_output.rename(columns={"Quantity on Hand_Match": "Quantity on Hand"}, inplace=True)
   
        
        # ✅ Ensure All Expected D-Tools Columns Exist
        expected_columns = list(df_output.columns)

        # Add missing columns without overwriting existing data
        for col in expected_columns:
            if col not in final_output.columns:
                final_output[col] = ""

        # ✅ Align Final Output to D-Tools Column Order
        final_output = final_output[expected_columns]

        # ✅ Remove Any Unnecessary Columns (Like Unnamed)
        final_output = final_output.loc[:, ~final_output.columns.str.contains("^Unnamed")]
       
        st.write(final_output)
       
       
        # ✅ Export to Excel in Memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            final_output.to_excel(writer, sheet_name="Final Inventory", index=False)

        excel_data = output.getvalue()

        # ✅ Single Download Button for Cleaned Excel File
        st.download_button(
            label="📥 Télécharger Inventaire Final (Excel)",
            data=excel_data,
            file_name="Inventaire_Final.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if st.button("🔙 Retour au début"):
            st.session_state["step"] = 1
            st.rerun()

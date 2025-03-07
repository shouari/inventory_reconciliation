import streamlit as st
import pandas as pd
import numpy as np
import re
import io
import itertools
from xlsxwriter import Workbook
from Levenshtein import ratio

# ✅ Initialize all session state variables before accessing them
if "step" not in st.session_state:
    st.session_state["step"] = 0  

if "qb_duplicate_queue" not in st.session_state:
    st.session_state["qb_duplicate_queue"] = []

if "dt_duplicate_queue" not in st.session_state:
    st.session_state["dt_duplicate_queue"] = []

if "qb_cleaned_data" not in st.session_state:
    st.session_state["qb_cleaned_data"] = pd.DataFrame()

if "dt_cleaned_data" not in st.session_state:
    st.session_state["dt_cleaned_data"] = pd.DataFrame()

if "qb_fuzzy_duplicates" not in st.session_state:
    st.session_state["qb_fuzzy_duplicates"] = []

if "dt_fuzzy_duplicates" not in st.session_state:
    st.session_state["dt_fuzzy_duplicates"] = []

if "exact_matches" not in st.session_state:
    st.session_state["exact_matches"] = pd.DataFrame()

if "fuzzy_queue" not in st.session_state:
    st.session_state["fuzzy_queue"] = []


# ------------------------- UTILITIES -------------------------
def normalize_sku(sku):
    """Normalize SKU by removing spaces, converting to uppercase, and standardizing format."""
    sku = sku.upper().strip()
    sku = re.sub(r'(?<!\d)[.]', '', sku)  # Remove dots except when followed by a digit
    sku = re.sub(r'\s+', '', sku)  # Remove extra spaces
    return sku

st.set_page_config(layout="wide")

st.title("📦 Outil de Réconciliation des Stocks")

# ---- File Upload ----
st.sidebar.header("Étape 1: Importer les fichiers")
qb_file = st.sidebar.file_uploader("📘 Inventaire QuickBooks", type=["csv", "xlsx"])
dt_file = st.sidebar.file_uploader("📗 Inventaire D-Tools", type=["csv", "xlsx"])

# ------------------------- FUZZINESS SLIDER -------------------------
st.sidebar.header("🎚️ Réglage du Niveau de Correspondance")
fuzziness_threshold = st.sidebar.slider(
    "Ajustez le niveau de correspondance approximative :",
    min_value=0.80, max_value=1.0, step=0.01, value=0.95,
    help="0.80 = correspondance plus large, 1.0 = correspondance stricte."
)

st.sidebar.write(f"🔍 **Niveau de correspondance sélectionné** : {fuzziness_threshold:.2f}")

# ------------------------- START PROCESS BUTTON -------------------------

start_process = st.sidebar.button("🚀 Lancer le Nettoyage des Données")

if start_process:
    st.session_state["step"] = 1
step = st.session_state["step"]

if start_process and qb_file and dt_file:
    with st.spinner("📊 Chargement des données en cours..."):
        # Load Data (Ensure SKU is string)
        df_qb = pd.read_csv(qb_file, sep=";", dtype=str) if qb_file.name.endswith('.csv') else pd.read_excel(qb_file, dtype=str)
        df_dt = pd.read_csv(dt_file, sep=";", dtype=str) if dt_file.name.endswith('.csv') else pd.read_excel(dt_file, dtype=str)

        # Normalize SKUs
        df_qb["SKU_NORM"] = df_qb["SKU"].astype(str).str.strip().str.upper().apply(normalize_sku)
        df_dt["SKU_NORM"] = df_dt["SKU"].astype(str).str.strip().str.upper().apply(normalize_sku)

        # Initialize Session State Properly
        
        st.session_state["qb_duplicate_queue"] = df_qb["SKU_NORM"][df_qb.duplicated("SKU_NORM", keep=False)].unique().tolist()
        st.session_state["qb_cleaned_data"] = df_qb.copy()

       
        st.session_state["dt_duplicate_queue"] = df_dt["SKU_NORM"][df_dt.duplicated("SKU_NORM", keep=False)].unique().tolist()
        st.session_state["dt_cleaned_data"] = df_dt.copy()

        # **🚀 Optimized Fuzzy Matching Using itertools**
        def fast_fuzzy_match(sku_list, threshold):
            """Optimized fuzzy matching using itertools to reduce comparisons."""
            return [(sku1, sku2) for sku1, sku2 in itertools.combinations(sku_list, 2) if ratio(sku1, sku2) > threshold]

        
        st.session_state["qb_fuzzy_duplicates"] = fast_fuzzy_match(df_qb["SKU_NORM"].unique(), fuzziness_threshold)
        
        st.session_state["dt_fuzzy_duplicates"] = fast_fuzzy_match(df_dt["SKU_NORM"].unique(), fuzziness_threshold)

# ------------------------- STEP 1: CLEAN QuickBooks FIRST -------------------------
if step == 1 and qb_file and dt_file:
    st.header("🔍 Étape 1: Nettoyage des fichiers individuels (QuickBooks)")

    total_duplicates_qb = len(st.session_state["qb_duplicate_queue"])
    total_fuzzy_qb = len(st.session_state["qb_fuzzy_duplicates"])

    st.subheader(f"📘 QuickBooks: {total_duplicates_qb} exacts, {total_fuzzy_qb} approximatifs")

    if len(st.session_state["qb_duplicate_queue"]) > 0:
        current_sku = st.session_state["qb_duplicate_queue"][0]
        df_duplicate_group_qb = st.session_state["qb_cleaned_data"][st.session_state["qb_cleaned_data"]["SKU_NORM"] == current_sku]

        st.subheader(f"🛠️ Gestion des doublons (QuickBooks) - SKU: `{current_sku}`")
        st.dataframe(df_duplicate_group_qb)

        keep_sku = st.selectbox("Sélectionnez le SKU à conserver", df_duplicate_group_qb["SKU"].unique(), key=f"qb_keep_sku_{current_sku}")
        custom_sku = st.text_input("Ou entrez un nouveau SKU standardisé:", "", key=f"qb_custom_sku_{current_sku}")

        action = st.radio("Choisissez une action:", ["✅ Garder", "🟡 Fusionner (somme quantités)", "🔴 Supprimer"], key=f"qb_action_{current_sku}")

        if st.button("Suivant ➡️", key=f"qb_next_{current_sku}"):
            selected_sku = custom_sku if custom_sku else keep_sku

            if action == "🟡 Fusionner (somme quantités)":
                sum_quantity = df_duplicate_group_qb["Quantité en stock"].astype(float).sum()
                st.session_state["qb_cleaned_data"].loc[st.session_state["qb_cleaned_data"]["SKU_NORM"] == current_sku, "SKU"] = selected_sku
                st.session_state["qb_cleaned_data"].loc[st.session_state["qb_cleaned_data"]["SKU_NORM"] == selected_sku, "Quantité en stock"] = sum_quantity

            elif action == "🔴 Supprimer":
                st.session_state["qb_cleaned_data"] = st.session_state["qb_cleaned_data"][st.session_state["qb_cleaned_data"]["SKU_NORM"] != current_sku]

            st.session_state["qb_duplicate_queue"].pop(0)
            st.rerun()
        # ✅ Process Fuzzy Duplicates for QuickBooks
    elif len(st.session_state["qb_fuzzy_duplicates"]) > 0:
        fuzzy_sku1, fuzzy_sku2 = st.session_state["qb_fuzzy_duplicates"][0]
        df_fuzzy_group_qb = st.session_state["qb_cleaned_data"][st.session_state["qb_cleaned_data"]["SKU_NORM"].isin([fuzzy_sku1, fuzzy_sku2])]

        st.subheader(f"🔍 Correspondance Approximative (QuickBooks)")
        st.dataframe(df_fuzzy_group_qb)

        keep_sku = st.selectbox("Sélectionnez le SKU à conserver", df_fuzzy_group_qb["SKU"].unique(), key=f"qb_fuzzy_keep_{fuzzy_sku1}_{fuzzy_sku2}")
        custom_sku = st.text_input("Ou entrez un nouveau SKU standardisé:", "", key=f"qb_fuzzy_custom_sku_{fuzzy_sku1}_{fuzzy_sku2}")

        confirm = st.radio(f"Fusionner `{fuzzy_sku1}` et `{fuzzy_sku2}` ?", ["❌ Non", "✅ Oui"], key=f"qb_fuzzy_{fuzzy_sku1}_{fuzzy_sku2}")

        if st.button("Suivant ➡️", key=f"qb_fuzzy_next_{fuzzy_sku1}"):
            if confirm == "✅ Oui":
                sum_quantity = df_fuzzy_group_qb["Quantité en stock"].astype(float).sum()
                st.session_state["qb_cleaned_data"].loc[st.session_state["qb_cleaned_data"]["SKU_NORM"] == fuzzy_sku1, "Quantité en stock"] = sum_quantity

            st.session_state["qb_fuzzy_duplicates"].pop(0)
            st.rerun()

    if len(st.session_state["qb_duplicate_queue"]) == 0 and len(st.session_state["qb_fuzzy_duplicates"]) == 0:
        st.session_state["step"] = 1.5  # Move to D-Tools after QuickBooks is done
        st.rerun()

# ------------------------- STEP 1.5: Transition from QuickBooks to D-Tools -------------------------
if step == 1.5:
    st.subheader("✅ QuickBooks traité, passage à D-Tools...")
    st.session_state["step"] = 1.6
    st.rerun()

# ------------------------- STEP 1.6: CLEAN D-Tools AFTER QuickBooks -------------------------
if step == 1.6:
    st.header("🔍 Étape 1: Nettoyage des fichiers individuels (D-Tools)")

    total_duplicates_dt = len(st.session_state["dt_duplicate_queue"])
    total_fuzzy_dt = len(st.session_state["dt_fuzzy_duplicates"])

    st.subheader(f"📗 D-Tools: {total_duplicates_dt} exacts, {total_fuzzy_dt} approximatifs")

    if len(st.session_state["dt_duplicate_queue"]) > 0:
        current_sku = st.session_state["dt_duplicate_queue"][0]
        df_duplicate_group_dt = st.session_state["dt_cleaned_data"][st.session_state["dt_cleaned_data"]["SKU_NORM"] == current_sku]

        st.subheader(f"🛠️ Gestion des doublons (D-Tools) - SKU: `{current_sku}`")
        st.dataframe(df_duplicate_group_dt)

        keep_sku = st.selectbox("Sélectionnez le SKU à conserver", df_duplicate_group_dt["SKU"].unique(), key=f"dt_keep_sku_{current_sku}")
        custom_sku = st.text_input("Ou entrez un nouveau SKU standardisé:", "", key=f"dt_custom_sku_{current_sku}")

        action = st.radio("Choisissez une action:", ["✅ Garder", "🟡 Fusionner (somme quantités)", "🔴 Supprimer"], key=f"dt_action_{current_sku}")

        if st.button("Suivant ➡️", key=f"dt_next_{current_sku}"):
            selected_sku = custom_sku if custom_sku else keep_sku

            if action == "🟡 Fusionner (somme quantités)":
                sum_quantity = df_duplicate_group_dt["Quantity on Hand"].astype(float).sum()
                st.session_state["dt_cleaned_data"].loc[st.session_state["dt_cleaned_data"]["SKU_NORM"] == current_sku, "SKU"] = selected_sku
                st.session_state["dt_cleaned_data"].loc[st.session_state["dt_cleaned_data"]["SKU_NORM"] == selected_sku, "Quantity on Hand"] = sum_quantity

            elif action == "🔴 Supprimer":
                st.session_state["dt_cleaned_data"] = st.session_state["dt_cleaned_data"][st.session_state["dt_cleaned_data"]["SKU_NORM"] != current_sku]

            st.session_state["dt_duplicate_queue"].pop(0)
            st.rerun()

             # ✅ Process Fuzzy Duplicates for QuickBooks
    elif len(st.session_state["dt_fuzzy_duplicates"]) > 0:
        fuzzy_sku1, fuzzy_sku2 = st.session_state["dt_fuzzy_duplicates"][0]
        df_fuzzy_group_dt = st.session_state["dt_cleaned_data"][st.session_state["dt_cleaned_data"]["SKU_NORM"].isin([fuzzy_sku1, fuzzy_sku2])]

        st.subheader(f"🔍 Correspondance Approximative (D-Tools)")
        st.dataframe(df_fuzzy_group_dt)

        keep_sku = st.selectbox("Sélectionnez le SKU à conserver", df_fuzzy_group_dt["SKU"].unique(), key=f"dt_fuzzy_keep_{fuzzy_sku1}_{fuzzy_sku2}")
        custom_sku = st.text_input("Ou entrez un nouveau SKU standardisé:", "", key=f"dt_fuzzy_custom_sku_{fuzzy_sku1}_{fuzzy_sku2}")

        confirm = st.radio(f"Fusionner `{fuzzy_sku1}` et `{fuzzy_sku2}` ?", ["❌ Non", "✅ Oui"], key=f"dt_fuzzy_{fuzzy_sku1}_{fuzzy_sku2}")

        if st.button("Suivant ➡️", key=f"dt_fuzzy_next_{fuzzy_sku1}"):
            if confirm == "✅ Oui":
                sum_quantity = df_fuzzy_group_dt["Quantity on Hand"].astype(float).sum()
                st.session_state["dt_cleaned_data"].loc[st.session_state["dt_cleaned_data"]["SKU_NORM"] == fuzzy_sku1, "Quantity on Hand"] = sum_quantity

            st.session_state["dt_fuzzy_duplicates"].pop(0)
            st.rerun()

        # ✅ Download Cleaned Files
    if len(st.session_state["dt_duplicate_queue"]) == 0 and len(st.session_state["dt_fuzzy_duplicates"]) == 0:
        st.session_state["dt_cleanup_done"] = True  # ✅ Store cleanup completion flag
        st.success("✅ Tous les doublons ont été traités pour D-Tools !")

        cleaned_dt = st.session_state["dt_cleaned_data"].to_csv(index=False, sep=";").encode("utf-8")
        cleaned_qb = st.session_state["qb_cleaned_data"].to_csv(index=False, sep=";").encode("utf-8")

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
            label="📥 Télécharger D-Tools Nettoyé",
            data=cleaned_dt,
            file_name="DTools_Cleaned.csv",
            mime="text/csv"
        )
        with col2:
            st.download_button(
                label="📥 Télécharger QuickBooks Nettoyé",
                data=cleaned_qb,
                file_name="QuickBooks_Cleaned.csv",
                mime="text/csv"
            )

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
    df_qb = st.session_state.get("qb_cleaned_data", pd.DataFrame())  # Ensure df_qb exists

    # st.write("Columns in df_output:", df_output.columns.tolist())
    
    # ✅ Identify QuickBooks "Quantité en stock" column dynamically
    qb_qty_col = next((col for col in df_qb.columns if "Quantité en stock" or "Quantity on" in col), None)
   

    if qb_qty_col:
        df_qb.rename(columns={qb_qty_col: "Quantity on Hand"}, inplace=True)
    else:
        st.warning("⚠️ 'Quantité en stock' column not found in QuickBooks data. Proceeding without it.")

    # ✅ Merge QuickBooks Quantities into D-Tools Dataset
    st.write("Columns in df_qb:", df_qb.columns.tolist())
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

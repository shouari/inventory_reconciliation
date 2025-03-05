import streamlit as st
import pandas as pd
from Levenshtein import ratio
import hashlib
import itertools


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
        exact_matches = df_qb.drop_duplicates(subset="SKU")[df_qb["SKU"].isin(df_dt["SKU"])]
        st.session_state["exact_matches"] = exact_matches

        with st.expander(f"✅ {len(exact_matches)} Correspondances Exactes (Afficher / Masquer)"):
            st.dataframe(exact_matches)

        

         # ---- Mismatches ----
        mismatched_qb = df_qb.drop_duplicates(subset="SKU")[~df_qb["SKU"].isin(df_dt["SKU"])]
        mismatched_dt = df_dt.drop_duplicates(subset="SKU")[~df_dt["SKU"].isin(df_qb["SKU"])]

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
                if 80 < ratio(qb_sku, dt_sku) * 100 < 100 and qb_sku != dt_sku
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

        if st.button("🔙 Retour à l'etape 2"):
            st.session_state["step"] = 2
            st.rerun()


        exact_match_csv = st.session_state["exact_matches"].to_csv(index=False).encode("utf-8")
        fuzzy_match_csv = pd.DataFrame(st.session_state["fuzzy_queue"]).to_csv(index=False).encode("utf-8")
        


        if "mismatched_qb" in st.session_state and "mismatched_dt" in st.session_state:
            mismatch_qb_csv = st.session_state["mismatched_qb"].to_csv(index=False).encode("utf-8")
            mismatch_dt_csv = st.session_state["mismatched_dt"].to_csv(index=False).encode("utf-8")
        else:
            st.error("Les données des SKU non correspondants ne sont pas disponibles. Veuillez repasser par l'étape 2.")
            st.stop()


        col1, col2 = st.columns(2)
        with col1:
            st.download_button("📥 Télécharger Correspondances Exactes", data=exact_match_csv, file_name="exact_matches.csv", mime="text/csv")
            st.download_button("📥 Télécharger Fuzzy Matches", data=fuzzy_match_csv, file_name="fuzzy_matches.csv", mime="text/csv")
        with col2:
            st.download_button("📥 Télécharger QuickBooks Mismatches", data=mismatch_qb_csv, file_name="quickbooks_mismatches.csv", mime="text/csv")
            st.download_button("📥 Télécharger D-Tools Mismatches", data=mismatch_dt_csv, file_name="dtools_mismatches.csv", mime="text/csv")

        if st.button("🔙 Retour au début"):
            st.session_state["step"] = 1
            st.rerun()
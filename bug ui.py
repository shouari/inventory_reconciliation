import streamlit as st
import pandas as pd
from Levenshtein import ratio
import numpy as np

st.set_page_config(page_title="📦 Outil de Réconciliation des Stocks", page_icon=":package:", layout="wide")

# Step 1: File Upload
st.sidebar.header("Étape 1: Importer les fichiers")
qb_file = st.sidebar.file_uploader("📘 Inventaire QuickBooks", type=["csv", "xlsx"])
dt_file = st.sidebar.file_uploader("📗 Inventaire D-Tools", type=["csv", "xlsx"])

# Pagination Function
def paginate_dataframe(df, page_size=100, key_prefix=""):
    total_pages = max(1, np.ceil(len(df) / page_size).astype(int))
    page_number = st.session_state.get(f"{key_prefix}_page_number", 1)

    if page_number > total_pages:
        page_number = 1  

    start_idx, end_idx = (page_number - 1) * page_size, min(page_number * page_size, len(df))
    df_page = df.iloc[start_idx:end_idx]

    col1, col2, col3 = st.columns([1, 4, 1])
    if col1.button("⬅️ Précédent", key=f"{key_prefix}_prev") and page_number > 1:
        st.session_state[f"{key_prefix}_page_number"] = page_number - 1
        st.rerun()
    col3.write(f"📄 Page {page_number} / {total_pages}")
    if col3.button("➡️ Suivant", key=f"{key_prefix}_next") and page_number < total_pages:
        st.session_state[f"{key_prefix}_page_number"] = page_number + 1
        st.rerun()

    return df_page

if qb_file and dt_file:
    df_qb = pd.read_csv(qb_file, sep=";", dtype=str) if qb_file.name.endswith('.csv') else pd.read_excel(qb_file, dtype=str)
    df_dt = pd.read_csv(dt_file, sep=";", dtype=str) if dt_file.name.endswith('.csv') else pd.read_excel(dt_file, dtype=str)

    df_qb["SKU"] = df_qb["SKU"].astype(str).str.strip().str.upper()
    df_dt["SKU"] = df_dt["SKU"].astype(str).str.strip().str.upper()

    if "step" not in st.session_state:
        st.session_state["step"] = 1

    step = st.session_state["step"]

    # ------------------------- STEP 1: CLEAN INDIVIDUAL FILES -------------------------
    if step == 1:
        st.header("🔍 Étape 1: Nettoyage des fichiers")

        def process_duplicates(df, source_name, key_prefix):
            """Highlight duplicates and allow bulk actions."""
            st.subheader(f"🛠️ Gestion des doublons - {source_name}")

                        # Identify True Duplicates (SKUs appearing 2+ times)
            duplicate_counts = df["SKU"].value_counts()
            true_duplicates = duplicate_counts[duplicate_counts > 1].index.tolist()
            dupes = df[df["SKU"].isin(true_duplicates)].copy()

            if not dupes.empty:
                st.write(f"⚠️ {len(dupes)} doublons détectés.")

                # Move "Statut" next to "Sélectionner"
                dupes.insert(0, "Sélectionner", False)
                dupes.insert(1, "🛑 Statut", "❗ Doublon")

                # Alternating Colors for Groups (Fixing Display Issue)
                colors = []
                for sku in dupes["SKU"]:
                    index = true_duplicates.index(sku) if sku in true_duplicates else 0
                    color = "#ffb3b3" if index % 2 == 0 else "#ff6666"
                    colors.append(f"background-color: {color}")

                dupes_page = paginate_dataframe(dupes, key_prefix=key_prefix)

                # ✅ Ensure color alternation applies correctly
                df_styled = dupes_page.style.apply(lambda _: colors[:len(dupes_page)], axis=0)

                # Display as Markdown to Apply Styling Properly
                st.markdown("### 📋 Liste des doublons")
                st.dataframe(df_styled)

                # Bulk Actions
                col1, col2, col3 = st.columns(3)
                if col1.button("🟡 Fusionner", key=f"{key_prefix}_merge"):
                    selected_skus = edited_df[edited_df["Sélectionner"]]["SKU"].unique()
                    df = df[~df["SKU"].isin(selected_skus)]
                    df = pd.concat([df, dupes[dupes["SKU"].isin(selected_skus)].drop(columns=["Sélectionner", "🛑 Statut"])], ignore_index=True)
                    st.rerun()
                if col2.button("🔴 Supprimer", key=f"{key_prefix}_delete"):
                    selected_skus = edited_df[edited_df["Sélectionner"]]["SKU"].unique()
                    df = df[~df["SKU"].isin(selected_skus)]
                    st.rerun()
                if col3.button("⚪ Ignorer", key=f"{key_prefix}_ignore"):
                    selected_skus = edited_df[edited_df["Sélectionner"]]["SKU"].unique()
                    df.loc[df["SKU"].isin(selected_skus), "🛑 Statut"] = "✅ Ignoré"
                    st.rerun()

                return df
            else:
                st.success(f"Aucun doublon trouvé dans {source_name}.")
                return df

        st.markdown("### 📘 QuickBooks Inventory")
        df_qb = process_duplicates(df_qb, "QuickBooks", key_prefix="qb")

        st.markdown("### 📗 D-Tools Inventory")
        df_dt = process_duplicates(df_dt, "D-Tools", key_prefix="dt")

        if st.button("🔜 Passer à l'étape 2"):
            st.session_state["df_qb_cleaned"] = df_qb
            st.session_state["df_dt_cleaned"] = df_dt
            st.session_state["step"] = 2
            st.rerun()

    # ------------------------- STEP 2: MATCH SKUs -------------------------
     if step == 2:
        st.header("🔍 Étape 2: Correspondance des SKUs")

        df_qb = st.session_state["qb_cleaned_data"]
        df_dt = st.session_state["dt_cleaned_data"]

        # ---- Exact Matches ----
        exact_matches = df_qb[df_qb["SKU"].isin(df_dt["SKU"])]
        with st.expander(f"✅ {len(exact_matches)} Correspondances Exactes (Afficher / Masquer)"):
            st.dataframe(exact_matches)

        # ---- Fuzzy Matches ----
        if "fuzzy_queue" not in st.session_state:
            fuzzy_matches = [
                {"QuickBooks SKU": qb_sku, "D-Tools SKU": dt_sku, "Similitude": round(ratio(qb_sku, dt_sku), 2)}
                for qb_sku in df_qb["SKU"]
                for dt_sku in df_dt["SKU"]
                if 0.8 < ratio(qb_sku, dt_sku) < 1 and qb_sku != dt_sku
            ]
            fuzzy_matches_df = pd.DataFrame(fuzzy_matches).sort_values(by="Similitude", ascending=False)
            st.session_state["fuzzy_queue"] = fuzzy_matches_df.to_dict(orient="records")
            st.session_state["fuzzy_selected"] = []

        # Handle Fuzzy Matches One-by-One
        if len(st.session_state["fuzzy_queue"]) > 0:
            fuzzy_match = st.session_state["fuzzy_queue"][0]
            st.subheader(f"⚠️ Correspondance Approximative")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.write("📘 **QuickBooks SKU**")
                st.write(f"🔵 `{fuzzy_match['QuickBooks SKU']}`")
            with col2:
                st.write("📗 **D-Tools SKU**")
                st.write(f"🟢 `{fuzzy_match['D-Tools SKU']}`")
            with col3:
                st.write("📊 **Similitude**")
                similarity = fuzzy_match['Similitude'] * 100
                color = f"background-color: rgba(255, {255-int(similarity*2.55)}, {255-int(similarity*2.55)}, 0.5); padding:5px; border-radius:5px;"
                st.markdown(f"<div style='{color}'>{similarity:.0f}%</div>", unsafe_allow_html=True)

            action = st.radio("Choisissez une action:", ["✅ Garder les deux", "🟡 Fusionner", "🔴 Ignorer"], key="fuzzy_action")

            if st.button("Suivant ➡️"):
                if action == "🟡 Fusionner":
                    st.session_state["fuzzy_selected"].append(fuzzy_match["QuickBooks SKU"])
                    df_dt = df_dt[df_dt["SKU"] != fuzzy_match["D-Tools SKU"]]

                elif action == "✅ Garder les deux":
                    st.session_state["fuzzy_selected"].append(fuzzy_match["QuickBooks SKU"])
                    st.session_state["fuzzy_selected"].append(fuzzy_match["D-Tools SKU"])

                st.session_state["fuzzy_queue"].pop(0)
                st.session_state["df_dt_cleaned"] = df_dt
                st.rerun()

        else:
            st.success("✅ Toutes les correspondances approximatives ont été traitées !")

            # ---- Total Mismatches ----
            mismatched_qb = df_qb[~df_qb["SKU"].isin(df_dt["SKU"])]
            mismatched_dt = df_dt[~df_dt["SKU"].isin(df_qb["SKU"])]
            total_mismatches = len(mismatched_qb) + len(mismatched_dt)

            st.subheader(f"🔍 {total_mismatches} SKU Non Correspondants")

            mismatch_mode = st.radio("Comment gérer ces SKU ?", ["🟢 Ajouter Tous", "🟡 Sélectionner Manuellement", "🔴 Ignorer Tous"], key="mismatch_action")

            if mismatch_mode == "🟡 Sélectionner Manuellement":
                st.markdown("### 📘 QuickBooks SKU Non Correspondants")
                selected_qb = st.multiselect("Sélectionnez les SKU QuickBooks à ajouter", mismatched_qb["SKU"].tolist())

                st.markdown("### 📗 D-Tools SKU Non Correspondants")
                selected_dt = st.multiselect("Sélectionnez les SKU D-Tools à ajouter", mismatched_dt["SKU"].tolist())

            if st.button("🔜 Passer à l'étape 3"):
                if mismatch_mode == "🟢 Ajouter Tous":
                    st.session_state["selected_mismatches"] = pd.concat([mismatched_qb, mismatched_dt])

                elif mismatch_mode == "🟡 Sélectionner Manuellement":
                    st.session_state["selected_mismatches"] = pd.concat([
                        mismatched_qb[mismatched_qb["SKU"].isin(selected_qb)],
                        mismatched_dt[mismatched_dt["SKU"].isin(selected_dt)]
                    ])

                else:
                    st.session_state["selected_mismatches"] = pd.DataFrame()

                st.session_state["step"] = 3
                st.rerun()

    # ------------------------- STEP 3: FINALIZE & EXPORT -------------------------
    if step == 3:
        st.header("📤 Étape 3: Finalisation & Export")
        df_final = pd.concat([st.session_state["df_qb_cleaned"], st.session_state["df_dt_cleaned"]], ignore_index=True)

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

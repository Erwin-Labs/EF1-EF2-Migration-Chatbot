import streamlit as st
import json
import yaml
from groq import Groq
import re
import textwrap
from typing import Dict, Any, Optional

# -----------------------------------------------------------------------------
#  Dynatrace EF1 → EF2 Converter – Streamlit App
# -----------------------------------------------------------------------------
#  - Interface Streamlit
#  - DynatraceConverter : appel Groq + prompt système unique
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="Convertisseur Dynatrace EF1 → EF2",
    page_icon="🔄",
    layout="wide",
)


class DynatraceConverter:
    """Appelle le modèle Groq et normalise la réponse YAML."""

    def __init__(self, groq_api_key: str):
        self.client = Groq(api_key=groq_api_key)

    # ------------------------- Conversion EF1 → EF2 -------------------------
    def convert_ef1_to_ef2(self, ef1_code: str, system_prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
        user_prompt = f"```json\n{ef1_code}\n```"
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except Exception as e:
            return f"Erreur lors de la conversion : {e}"

    # ------------------------------- Utils -----------------------------------
    @staticmethod
    def validate_json(text: str) -> bool:
        try:
            json.loads(text)
            return True
        except json.JSONDecodeError:
            return False

    @staticmethod
    def normalize_yaml(yaml_str: str) -> str:
        """Supprime les indentations communes + espaces en début de chaîne."""
        return textwrap.dedent(yaml_str).lstrip("\n").rstrip()


# -----------------------------------------------------------------------------
#  Interface Streamlit
# -----------------------------------------------------------------------------

def edit_prompt_modal():
    """Affiche une modale pour éditer et sauvegarder le prompt système."""
    if 'show_modal' not in st.session_state:
        st.session_state.show_modal = False

    if st.button("⚙️ Éditer le prompt système", key="edit_prompt"):
        st.session_state.show_modal = True

    if st.session_state.show_modal:
        with st.container():
            st.markdown("### Éditeur de Prompt Système")
            edited_prompt = st.text_area(
                "Prompt:",
                value=st.session_state.system_prompt,
                height=400,
                key="prompt_editor"
            )
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Enregistrer", key="save_prompt"):
                    st.session_state.system_prompt = edited_prompt
                    st.session_state.show_modal = False
                    st.rerun()
            with col2:
                if st.button("Annuler", key="cancel_prompt"):
                    st.session_state.show_modal = False
                    st.rerun()

def main():
    st.title("🔄 Convertisseur Dynatrace EF1 → EF2")

    # Initialiser le prompt système et le modèle dans l'état de session
    if 'system_prompt' not in st.session_state:
        st.session_state.system_prompt = (
            f"""You are a file-format converter that turns Dynatrace Extension Framework 1 (EF1) **plugin.json** files into fully valid Extension Framework 2 (EF2) **extension.yaml** files.  
                You know nothing about Dynatrace beyond what is written here. Break **any** rule and the result is invalid. Produce flawless YAML.

                ────────────────────────────────────────────────────────\n
                GLOBAL OUTPUT RULES
                1. **Return ONLY raw YAML**—no Markdown fences, comments, or extra text.  
                2. **Indent with 2 spaces** (never tabs).  
                3. **Quoting**  
                • Wrap any scalar containing a special character (`: * {{ }} , ? [ ] & # | > ! % @` or a space) in *single* quotes.  
                • Always wrap `minDynatraceVersion` in *double* quotes.  
                4. **Metric-key syntax**  
                • Exactly **one** colon after the extension name: `custom:<ext-name>.<rest.of.key>`  
                    - Example → `custom:jmx-tomcat-monitoring.jvm.thread_count`  
                5. **Extension name**: If the EF1 `name` lacks a vendor/custom prefix, prepend `custom:` automatically.

                ────────────────────────────────────────────────────────\n
                STEP-BY-STEP CONVERSION

                ▸ **Root fields**
                ```yaml
                name:        <converted or prefixed EF1 name>
                version:     <EF1 version>
                minDynatraceVersion: "1.272"
                author:
                name: Dynatrace Migration Bot
                ````

                ▸ **metrics** (metadata-only)
                For every EF1 `metrics` element:

                ```yaml
                metrics:
                - key: <correct-format metric key>
                    metadata:
                    displayName: '<timeseries.displayname>'
                    unit: <unit | 'Millisecond' if EF1 unit == 'MilliSecond'>
                ```

                ▸ **jmx** (data collection)\n

                ```yaml
                jmx:
                groups:
                    - group: <source.domain>
                    subgroups:
                        - subgroup: <clear subgroup label>
                        query: '<domain>:<k1>=<v1>,<k2>=\'*\'>'
                        queryFilters:       # optional
                            - field: <field>
                            filter: var:<varId>
                        metrics:
                            - key: <metric key>
                            type: <count|gauge>            # count when attribute == CollectionCount
                            value: '<attribute|attribute:Composite,key:subField>'
                        dimensions:         # only if EF1 had splitting (NEVER rx_pid)
                            - key: <splitting.name>
                            value: 'property:<keyAfter>'
                ```\n

                *Rules*
                • **No `interval`** inside any JMX block.
                • `rx_pid` dimension is forbidden (created automatically by OneAgent).
                • Composite attributes must be written `'attribute:SomeAttr,key:subField'`.
                • Do **not** add a separate dimension for the same composite sub-field.

                ▸ **vars** (Settings 2.0)\n

                ```yaml
                vars:
                - id: <property.key>
                    type: <string|password|dropdown>          # lowercase
                    displayName: '<property.displayname>'
                    required: <true|false>
                    defaultValue: '<property.default>'        # if present
                    maxLength: <property.maxlength>           # if present
                    availableValues:                          # dropdown only
                    - label: '<option.label>'
                        value: '<option.value>'
                ```\n

                ────────────────────────────────────────────────────────\n
                VALIDATION CHECKLIST (internal)
                ✔ No backticks, headers, or comments in final YAML  
                ✔ Exactly one colon in every metric key  
                ✔ All scalars containing `:` or `*` are single-quoted  
                ✔ No `interval` in JMX, no `rx_pid` dimension  
                ✔ Composite metrics written with `attribute:<attr>,key:<part>` and *no* extra dimension  
                ✔ Units corrected (`MilliSecond` → `Millisecond`)  
                ✔ Limits respected (≤10 groups, ≤10 subgroups each, ≤100 metrics, ≤25 dimensions per level)
                ```\n

                ---\n""")
    
    # Initialiser le modèle sélectionné dans l'état de session
    if 'selected_model' not in st.session_state:
        st.session_state.selected_model = "llama-3.3-70b-versatile"

    col1, col2, col3 = st.columns([1, 3, 3])

    with col1:
        st.header("⚙️ Configuration")
        groq_api_key = st.text_input("Clé API Groq", type="password")
        if groq_api_key:
            st.success("✅ Clé API Groq enregistrée")
        
        edit_prompt_modal()
        
        # Sélection du modèle
        st.markdown("### 🤖 Modèle")
        available_models = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "meta-llama/llama-4-maverick-17b-128e-instruct"
        ]
        
        selected_model = st.selectbox(
            "Choisir le modèle:",
            available_models,
            index=available_models.index(st.session_state.selected_model),
            key="model_selector"
        )
        
        # Mettre à jour le modèle sélectionné
        if selected_model != st.session_state.selected_model:
            st.session_state.selected_model = selected_model
        
        st.markdown("---")
        st.markdown("**Formats pris en charge :** plugin.json JMX")
        st.markdown("*Cette application convertit les extensions Dynatrace EF1 (plugin.json et JMX) en YAML valide pour EF2.*")

    with col2:
        st.header("📥 Extension EF1 (JSON)")
        ef1_input = st.text_area('Collez le JSON EF1 puis cliquez sur "Convertir"', height=450)
        json_valid = False
        if ef1_input:
            if DynatraceConverter.validate_json(ef1_input):
                st.success("✅ JSON valide")
                json_valid = True
            else:
                st.error("❌ JSON invalide")

    with col3:
        st.header("📤 Extension EF2 (YAML)")
        if st.button("Convertir", key="convert", disabled=not (groq_api_key and ef1_input and json_valid)):
            conv = DynatraceConverter(groq_api_key)
            with st.spinner("Conversion en cours…"):
                raw_yaml = conv.convert_ef1_to_ef2(ef1_input, st.session_state.system_prompt, st.session_state.selected_model)
                yaml_clean = conv.normalize_yaml(raw_yaml)
                st.text_area("YAML EF2", yaml_clean, height=450)
                try:
                    yaml.safe_load(yaml_clean)
                    st.success("✅ YAML valide")
                    st.download_button("💾 Télécharger extension.yaml", yaml_clean, "extension.yaml", "text/yaml", key="download")
                except yaml.YAMLError as e:
                    st.error(f"⚠️ YAML invalide : {e}")

    st.markdown("---")
    st.markdown("💡 *Application de démonstration technologique proposée par Erwin Labs SAS, qui n'a pas pour objectif d'être utilisée en production.*")


if __name__ == "__main__":
    main()

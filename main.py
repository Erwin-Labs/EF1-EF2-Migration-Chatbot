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

        # ------------------------------------------------------------------
        # PROMPT SYSTÈME UNIQUE (22‑06‑2025) – corrigé : racine sans indentation.
        # ------------------------------------------------------------------
        self.system_prompt = (
            """You convert Dynatrace Extensions Framework 1 (EF1) JMX extensions to valid Extensions Framework 2 (EF2) YAML.

"
            "=== HARD RULES ===============================================================
"
            "1. **Output**: return only EF2 YAML – no markdown, no code‑block fences.
"
            "2. **Root alignment**: top‑level keys (`name`, `version`, etc.) **MUST** start at column 0 – no leading spaces.
"
            "3. **Indent**: exactly 2 spaces per level, no tabs.
"
            "4. **Top‑level `metrics` list**: each item contains ONLY `key` + `metadata`.
"
            "   · NEVER include `type`, `value`, `dimensions`, or `query` at root level.
"
            "5. **`jmx.groups[].subgroups[].metrics[]` items**: 
"
            "   · Fields allowed: `key`, `type`, `value`, `dimensions`.
"
            "6. **Dimensions syntax**:
"
            "   · Every dimension is a dict **with two fields**: `key` and `value`.
"
            "   · Example:  - key: gc_name
                   value: property:name
"
            "   · Do NOT output wildcard aliases like `- name: *`. If a wildcard is needed, handle via the `query` string ONLY.
"
            "   · `value` must be `property:<propName>` or a quoted constant.
"
            "7. Remove dimension `rx_pid`; drop the `dimensions` block if it becomes empty.
"
            "8. Use `type: count` for monotonically increasing attributes (e.g. CollectionCount).
"
            "9. **Queries**: format `<domain>:<k>=<v>[,<k>=<v>...]`, keep wildcards `*` INSIDE the query string.
"
            "10. Add inline `# TODO: verify` for any ambiguous field (unit, description).
"
            "==============================================================================

"
            "Provide EF1 JSON. Return the EF2 YAML only – NO fences, NO root indentation.
"""
            """You convert Dynatrace Extensions Framework 1 (EF1) JMX extensions to valid Extensions Framework 2 (EF2) YAML.\n\n"
            "=== HARD RULES ===============================================================\n"
            "1. **Output**: return only EF2 YAML – no markdown, no code‑block fences.\n"
            "2. **Root alignment**: top‑level keys (`name`, `version`, etc.) **MUST** start at column 0 – no leading spaces.\n"
            "3. **Indent**: use exactly 2 spaces per level, no tabs.\n"
            "4. **Structure** (simplified):\n"
            "   name: custom:<ext-name>\n   version: <semver>\n   minDynatraceVersion: 1.230\n   author:\n     name: Dynatrace Migration Bot\n   metrics: ...\n   jmx: ...\n   vars: ...\n"
            "5. Build `query`, `value`, `dimensions` per mapping rules (context→property:context, name→property:name, etc.).\n"
            "6. Remove dimension `rx_pid`; drop the whole `dimensions` block if empty.\n"
            "7. Use `type: count` for monotonically increasing attributes (e.g. CollectionCount).\n"
            "==============================================================================\n\n"
            "Provide an EF1 JSON. Return the converted EF2 YAML only – NO fences, NO indentation before root.\n"""
        )

    # ------------------------- Conversion EF1 → EF2 -------------------------
    def convert_ef1_to_ef2(self, ef1_code: str) -> str:
        user_prompt = f"```json\n{ef1_code}\n```"
        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
            )
            content = response.choices[0].message.content or ""
            return content.strip()
        except Exception as e:
            return f"Erreur lors de la conversion : {e}"

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

def main():
    st.title("🔄 Convertisseur Dynatrace EF1 → EF2")

    with st.sidebar:
        st.header("⚙️ Configuration Groq")
        groq_api_key = st.text_input("Clé API Groq", type="password")
        if groq_api_key:
            st.success("✅ Clé API Groq enregistrée")
        st.markdown("---")
        st.markdown("**Formats pris en charge :** plugin.json JMX")
        st.markdown("*Cette application convertit les extensions Dynatrace EF1 (plugin.json et JMX) en YAML valide pour EF2.*")

    col1, col2 = st.columns(2)

    with col1:
        st.header("📥 Extension EF1 (JSON)")
        ef1_input = st.text_area('Collez le JSON EF1 puis cliquez sur "Convertir", height=450)')
        if ef1_input and not DynatraceConverter.validate_json(ef1_input):
            st.error("❌ JSON invalide")
        elif ef1_input:
            st.success("✅ JSON valide")

    with col2:
        st.header("📤 Extension EF2 (YAML)")
        if st.button("Convertir", disabled=not (groq_api_key and ef1_input)):
            conv = DynatraceConverter(groq_api_key)
            with st.spinner("Conversion en cours…"):
                raw_yaml = conv.convert_ef1_to_ef2(ef1_input)
                yaml_clean = conv.normalize_yaml(raw_yaml)
                st.text_area("YAML EF2", yaml_clean, height=450)
                try:
                    yaml.safe_load(yaml_clean)
                    st.success("✅ YAML valide")
                    st.download_button("💾 Télécharger extension.yaml", yaml_clean, "extension.yaml", "text/yaml")
                except yaml.YAMLError as e:
                    st.error(f"⚠️ YAML invalide : {e}")

    st.markdown("---")
    st.markdown("💡 *Application de démonstration technologique proposée par Erwin Labs SAS, qui n'a pas pour objectif d'être utilisée en production.*")


if __name__ == "__main__":
    main()

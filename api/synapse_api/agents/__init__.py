"""Orchestrateur et casquettes (lot 3).

Les casquettes ne passent jamais par l'API HTTP : elles écrivent par `services`, donc par
les mêmes règles du cycle de vie que les humains. Elles parlent aux modèles par la seule
passerelle LiteLLM.
"""

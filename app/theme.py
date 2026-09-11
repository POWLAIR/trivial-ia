"""Constantes de présentation, définies une fois pour toutes les pages.

Une couleur par modèle, **identique sur toutes les pages** : la comparaison
visuelle d'une page à l'autre n'a de sens que si le codage couleur est stable.
C'est la raison d'être de ce module — une palette redéfinie localement dans
chaque vue finit par diverger, et le lecteur croit alors comparer deux modèles
alors qu'il compare deux nuances.
"""

from __future__ import annotations

from trivia_bench import config

# Palette qualitative, contrastée en clair comme en sombre.
_PALETTE = [
    "#4C78A8",
    "#F58518",
    "#54A24B",
    "#B279A2",
    "#E45756",
    "#72B7B2",
]

# Modèles connus du benchmark, dans l'ordre de taille croissante.
MODEL_ORDER = list(config.MODELS)
MODEL_COLORS = {name: _PALETTE[i % len(_PALETTE)] for i, name in enumerate(MODEL_ORDER)}

# Gris neutre : la ligne de hasard n'est pas un modèle, elle ne doit pas se lire
# comme une série de plus.
CHANCE_COLOR = "#7F7F7F"

MIN_SAMPLE = config.MIN_SAMPLE_FOR_RATE

# Les trois formats de tâche. Ils ne se comparent pas entre eux : fournir les
# options transforme une restitution en reconnaissance, et contraindre la sortie
# par grammaire force une réponse même sans connaissance.
FORMAT_FAMILY_ORDER = ["generation_libre", "qcm_options", "qcm_lettre"]

FORMAT_FAMILY_LABELS = {
    "generation_libre": "Génération libre",
    "qcm_options": "QCM, options fournies",
    "qcm_lettre": "QCM, réponse par lettre",
}

FORMAT_FAMILY_NOTES = {
    "generation_libre": (
        "Le modèle restitue la réponse sans aide. La ligne de hasard ne s'applique "
        "pas vraiment : rien ne force le modèle à proposer une des options, il peut "
        "donc tomber **sous** le hasard."
    ),
    "qcm_options": (
        "Les options sont fournies : la tâche devient une reconnaissance, ce qui "
        "relève mécaniquement le taux. Non comparable à la génération libre."
    ),
    "qcm_lettre": (
        "Les options sont fournies **et** la sortie est contrainte par grammaire à "
        "une seule lettre. Le modèle répond donc toujours, même quand il ignore "
        "tout : son score est plaqué sur la ligne du hasard par le bas au lieu de "
        "tomber en dessous. À ne jamais lire sans cette ligne."
    ),
}


def color_for(model: str) -> str:
    """Couleur stable d'un modèle, y compris s'il n'est pas déclaré dans config."""
    if model in MODEL_COLORS:
        return MODEL_COLORS[model]
    return _PALETTE[hash(model) % len(_PALETTE)]


def format_family_label(family: str) -> str:
    return FORMAT_FAMILY_LABELS.get(family, family)

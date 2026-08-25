"""Personas extra P19–P28 viven en cliente_hogareno.PERSONAS.

Filtro conveniente sin import circular. Lotes: importar desde qa_bot.lotes.
"""

from __future__ import annotations


def personas_extra():
    """P19–P28 del catálogo hogareño (lazy: evita ciclo al importar)."""
    from qa_bot.cliente_hogareno import PERSONAS

    return [p for p in PERSONAS if int(p.id[1:]) >= 19]


# Alias histórico (lista materializada al primer acceso vía __getattr__)
def __getattr__(name: str):
    if name == "PERSONAS_EXTRA":
        return personas_extra()
    raise AttributeError(name)

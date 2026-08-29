---
id: blueprint-internet_repetidor
collection: 01_soporte_internet
status: draft
rag_ready: false
review_required: technical,functional,privacy
---

# Repetidores Wi‑Fi domésticos

> Buenas prácticas N1 — extensores de cobertura en el hogar.

## Objetivo

Orientar al abonado cuando internet anda bien cerca del módem/router pero falla o va lento donde hay un repetidor/extensor.

## Reglas de oro

### Media distancia

No colocar el repetidor en la zona muerta sin señal. Ubicarlo a medio camino entre el router principal y la zona a cubrir, donde aún haya buena señal del router (> -65 dBm ideal).

### Modo Punto de Acceso (recomendado)

Conectar el repetidor al router con cable UTP Cat5e/Cat6 y configurarlo como AP. Mantiene el 100% de la velocidad contratada.

### Modo extensor inalámbrico (desaconsejado)

Repetidores 2.4 GHz pierden ~50% del rendimiento (half-duplex). La velocidad será menor que junto al router principal.

### SSID unificado

Mismo nombre de red y contraseña en el repetidor facilita el roaming entre habitaciones.

## Pasos N1

1. Confirmar que por cable al router navega bien.
2. Preguntar si tiene repetidor/extensor y dónde está enchufado.
3. Sugerir moverlo más cerca del router (media distancia).
4. Si persiste: probar cable UTP al repetidor en modo AP.
5. Desenchufar repetidores temporalmente para aislar si el problema es la línea o el extensor.

## Plantilla bot

«Si internet te anda bien cerca del módem principal pero lento donde tenés el repetidor, puede estar recibiendo débil la señal base. Probá mudarlo a un enchufe más cerca del router o conectarlo con cable de red.»

## Reglas de decisión

- Si cable al router OK y solo falla lejos con repetidor: `resolved/repetidor_ubicacion` o `resolved/cobertura_wifi`.
- Si también falla por cable: volver a flujo FTTH/radio/ADSL según tecnología.

# imowi Operations Hub

## Copilot operativo para cooperativas y NOC imowi

**imowi Operations Hub** es una plataforma agentic para centralizar la atencion de reclamos moviles de cooperativas revendedoras, guiando al operador N1, consultando contexto tecnico, clasificando incidentes y generando tickets auditables para el NOC o proveedores.

El objetivo no es reemplazar JSC ni los sistemas contables existentes, sino ordenar la operacion diaria entre cooperativas e imowi, reduciendo incertidumbre, evitando escalaciones incompletas y dejando trazabilidad de cada caso.

---

## Propuesta de valor

- Reduce la incertidumbre del operador N1 con pasos claros segun el tipo de reclamo.
- Estandariza criterios de resolucion en N1 y escalamiento a N2, carrier o proveedor.
- Genera tickets con historial tecnico de las pruebas realizadas antes de escalar.
- Permite operar multiples cooperativas con datos aislados por tenant.
- Entrega al NOC imowi una vista global de tickets, red, estadisticas y seguimiento.
- Combina reglas operativas, contexto JSC, base de conocimiento e IA cuando aporta valor.

---

## Que hace hoy el sistema

### Consola de soporte

El operador ingresa el reclamo en lenguaje natural, por ejemplo:

> Cliente sin datos en Brasil, linea 2235551234, Samsung A54.

A partir de ese mensaje, el sistema:

- Detecta linea, sintoma, dispositivo y contexto operativo.
- Consulta la ficha JSC disponible para esa linea.
- Clasifica el tipo de incidente.
- Muestra una guia operativa N1 paso a paso.
- Interpreta respuestas cortas del operador como "verificado", "ok", "sigue igual", "si persiste".
- Decide si corresponde continuar en N1, pedir mas datos o escalar.
- Crea tickets con ID y timeline cuando corresponde.

### Guia operativa por categoria

El sistema cuenta con playbooks operativos para distintos tipos de incidentes:

- Roaming internacional.
- Datos moviles / APN.
- Senal y cobertura.
- SMS / A2P.
- SIM / chip.
- Casos generales.

Cada playbook guia al operador por pasos concretos, evita repetir acciones innecesarias y registra lo confirmado en el historial del caso.

### Ficha JSC

Cuando la linea esta disponible en el catalogo operativo del tenant, la consola muestra:

- MSISDN.
- Abonado.
- Plan.
- Estado de linea.
- Estado de cuenta.
- Saldo/resumen.
- APN.
- Roaming habilitado.

Esto permite validar informacion tecnica antes de escalar a red o proveedor.

### Motor conversacional

El motor mantiene el estado del caso y entiende la conversacion de forma contextual:

- Reclamo nuevo.
- Recoleccion de datos.
- Guia de resolucion N1.
- Espera de confirmacion.
- Ticket creado.
- Caso cerrado como resuelto.

Tambien interpreta intenciones del operador, como:

- Confirmacion de paso.
- Persistencia del problema.
- Solicitud de ticket.
- Consulta por estado de ticket.
- Correccion del operador.
- Cierre por resolucion.
- Aporte de datos complementarios.

La logica no depende solamente de frases exactas: combina reglas, contexto del ultimo mensaje del bot, hechos acumulados e IA cuando es necesario.

---

## Clasificacion y escalamiento

El sistema clasifica los incidentes y define el destino operativo:

| Tipo de caso | Destino posible |
| --- | --- |
| Caso resoluble en N1 | Cooperativa |
| Roaming, datos o senal persistente | NOC imowi |
| SMS / A2P | Carrier |
| SIM / eSIM | Proveedor SIM |
| Provision / plataforma | Plataforma OSS/BSS |

Los tickets se crean con:

- ID operativo, por ejemplo `JSC-1005`.
- Nivel: N1, N2 o proveedor.
- Destino: cooperativa, NOC imowi, carrier u otro proveedor.
- Categoria.
- Motivo de escalamiento.
- Evidencia.
- Acciones N1 realizadas.
- Timeline de eventos.
- Estado y SLA.

---

## Tickets auditables

Cada ticket queda registrado con informacion estructurada para seguimiento:

- Descripcion del reclamo.
- Linea afectada.
- Categoria tecnica.
- Nivel y destino.
- Proveedor sugerido.
- Regla de clasificacion aplicada.
- Evidencia operativa.
- Timeline de pasos realizados.
- Notificaciones.
- Estado y resolucion tecnica.

El NOC puede actualizar el ticket, agregar avances, cambiar estado y documentar la resolucion.

---

## Vista NOC imowi

El usuario admin de imowi accede a una vista global con:

- Tablero de tickets priorizados.
- Estado, nivel, categoria y riesgo.
- Explicacion del escalamiento.
- Timeline de cada ticket.
- Monitor de red.
- Estadisticas operativas.
- Gestion de cooperativas y usuarios.
- Administracion de base de conocimiento.
- Auditoria de acciones.

Esta vista permite seguir la operacion completa entre cooperativas y NOC desde una unica consola.

---

## Monitor de red y proactividad

La plataforma incluye un monitor de elementos de red con telemetria operativa. Ante una anomalia activa, el sistema puede correlacionar sintomas del reclamo con el elemento afectado.

Capacidades actuales:

- Visualizacion de elementos de red.
- Estado y metrica actual.
- Simulacion de fallas para demo o validacion.
- Deteccion de anomalias correlacionadas.
- Creacion de tickets predictivos cuando corresponde.
- Alerta visible en consola de soporte.

---

## Base de conocimiento

El sistema cuenta con un centro de conocimiento administrable:

- Articulos por tenant/cooperativa.
- Procedimientos N1.
- Criterios de escalamiento.
- Excepciones operativas.
- Contexto tecnico para mejorar respuestas.
- Busqueda combinada con base documental historica.

La base de conocimiento alimenta al diagnostico, la guia del operador y las recomendaciones.

---

## Multitenancy y roles

La plataforma esta preparada para operar multiples cooperativas en una misma instalacion.

| Rol | Capacidades |
| --- | --- |
| Operador cooperativa | Atiende reclamos, usa chat, ve sus tickets y su contexto |
| Admin imowi / NOC | Vista global, tickets de todas las cooperativas, red, estadisticas y administracion |

Cada cooperativa tiene:

- Usuarios propios.
- Tickets propios.
- Casos conversacionales propios.
- Base de conocimiento propia.
- Branding visual configurable.

---

## Arquitectura productiva

La solucion se encuentra montada con arquitectura web moderna:

| Capa | Tecnologia | Funcion |
| --- | --- | --- |
| Frontend | Next.js en Vercel | Consola web de operador y admin |
| Backend | FastAPI en Render | API, agentes, motor conversacional y tickets |
| Base de datos | PostgreSQL | Casos, tickets, usuarios, KB, telemetria y auditoria |
| IA | LLM compatible OpenAI | Respuestas asistidas cuando corresponde |
| Deploy | GitHub + auto-deploy | Publicacion automatica desde rama principal |

Flujo general:

```text
Operador / NOC
    -> Consola web
    -> API FastAPI
    -> Motor conversacional + agentes
    -> PostgreSQL / JSC / KB / telemetria
    -> Respuesta y/o ticket auditable
```

---

## Modulos disponibles

### Para operadores

- Consola de soporte.
- Chat operativo.
- Guia N1 por categoria.
- Ficha JSC.
- Caso activo.
- Ticket en formacion.
- Timeline del ticket.
- Notificaciones.
- Nuevo reclamo.
- Registro de ticket NOC.

### Para admin imowi

- Tablero NOC.
- Monitor de red.
- Estadisticas.
- Administracion de cooperativas.
- Administracion de usuarios.
- Importacion CSV.
- Centro de conocimiento.
- Auditoria.
- Vista multi-tenant.

---

## Estado actual

El sistema se encuentra listo para un piloto controlado con operadores reales. Actualmente permite validar casos de operacion diaria, especialmente:

- Reclamos de roaming.
- Reclamos de datos moviles.
- Reclamos de senal/cobertura.
- Reclamos SMS/A2P.
- Consulta y seguimiento de tickets.
- Escalamiento N2.
- Vista NOC y actualizacion de tickets.

La recomendacion es probarlo con escenarios reales, midiendo:

- Si la guia ayuda al operador.
- Si el ticket generado contiene informacion suficiente.
- Si el NOC recibe contexto util para actuar.
- Si se reducen repreguntas y pasos incompletos.

---

## Acceso de prueba

**URL de la consola:**  
https://imowi-copilot.vercel.app

| Usuario | Perfil |
| --- | --- |
| `batan` | Operador Cooperativa Batan |
| `viamonte` | Operador Cooperativa Viamonte |
| `admin` | NOC imowi / vista global |

---

## Sugerencia de prueba

1. Ingresar como operador de cooperativa.
2. Crear un nuevo reclamo.
3. Probar un caso de roaming, datos, senal o SMS.
4. Seguir la guia operativa.
5. Confirmar persistencia si el problema continua.
6. Verificar que se cree ticket con ID.
7. Ingresar como admin imowi.
8. Revisar el ticket, timeline, destino y estado.

---

## Cierre

imowi Operations Hub propone una capa operativa entre cooperativas y NOC que transforma reclamos conversacionales en flujos guiados, tickets trazables y decisiones de escalamiento consistentes.

La plataforma ya permite demostrar valor operativo concreto: menos improvisacion en N1, mejor contexto para NOC y una base preparada para integrar automatizaciones futuras contra JSC, CRM, canales de notificacion y sistemas OSS/BSS.

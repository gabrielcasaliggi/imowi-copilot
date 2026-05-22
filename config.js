// Configuración del frontend (Netlify inyecta IMOWI_API_URL en el build).
// En local: vacío → el script usa el mismo origin o http://127.0.0.1:8000
window.IMOWI_API_URL = window.IMOWI_API_URL || '';

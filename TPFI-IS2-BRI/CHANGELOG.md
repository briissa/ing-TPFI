# Changelog

Los cambios importantes del proyecto se registran en este archivo.

## [0.1.0] - 2026-10-28

### Añadido

- Pruebas automatizadas de aceptación, validación, persistencia, auditoría y
  patrones de diseño.
- Verificación de cobertura de ramas con umbral mínimo del 85%.
- Documentación inicial del proyecto y workflow de controles en GitHub Actions.
- Diagramas UML de actividad del Proxy y de estados del Observer.
- Plantilla CookieCutter y migración del paquete a `src/tpfi`.
- Eliminación de la plantilla duplicada: el esqueleto se aplica al proyecto
  entregado, no se incluye un segundo TP dentro del repositorio.
- Plantilla CookieCutter y migración del paquete a `src/tpfi`.

### Corregido

- El cliente Observer conserva una referencia estable al socket durante la
  escucha, incluso cuando otra rutina cierra la conexión.

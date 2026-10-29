# Contexto y prompts del proyecto

## Enunciado

El proyecto debe implementar `SingletonClient`, `ObserverClient` y
`SingletonProxyObserverTPFI` en Python, conectados por TCP y respaldados por
DynamoDB. Debe aplicar Singleton para el acceso a `CorporateData` y
`CorporateLog`, Observer para las suscripciones y Proxy para las operaciones
auditadas.

Los entregables incluyen código modular, diagramas UML de actividad y estado,
casos de aceptación automatizados, pruebas Pytest con al menos 85% de
cobertura, documentación, licencia MIT, versión y build, controles Ruff, Black,
PEP 8/257, MyPy, Pyright y Bandit, dependencias declaradas y automatización
GitHub Actions.

## Prompts utilizados

- «Quiero que en base a ese enunciado, me digas qué cumple el TP. Seguido de eso
  quiero que me ayudes a terminarlo, pero cumpliendo con lo del TP. Creo que me
  faltan los casos de prueba, pero no sé si el enunciado dice cómo deberían
  ser».
- «El TP es TP1-IS2-BRI».

## Estado

Este archivo documenta el contexto y los prompts usados con asistencia de IA,
según lo solicitado por el enunciado. El estado de cumplimiento y las tareas
pendientes deben mantenerse alineados con `README.md` y `CHANGELOG.md`.

El proyecto está organizado con un esqueleto CookieCutter de tipo `src/`: el
paquete está en `src/tpfi`, los ejecutables permanecen en la raíz y las pruebas
están separadas en `tests/`. No se incluye una segunda copia del proyecto como
plantilla anidada.

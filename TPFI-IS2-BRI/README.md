# TP1-IS2-BRI

Implementación en Python del trabajo práctico final integrador de Ingeniería de
Software II. El sistema ofrece acceso a `CorporateData` mediante un servidor TCP,
usa DynamoDB para persistir datos y auditoría, y aplica los patrones Singleton,
Proxy y Observer.

## Requisitos

- Python 3.10 o superior.
- Tablas DynamoDB `CorporateData` y `CorporateLog` creadas previamente.
- Credenciales y región de AWS configuradas para boto3 al ejecutar contra AWS.

Para ejecutar pruebas sin AWS, el proyecto usa tablas en memoria mediante la
variable `TPFI_USE_MEMORY=1`.

## Instalación en Windows

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Ejecución

Iniciar el servidor:

```powershell
python singletonproxyobserver.py -p 8080
```

Enviar una operación (`get`, `set` o `list`):

```powershell
python singletonclient.py -i examples\get.json -s localhost -p 8080
```

Suscribirse a cambios:

```powershell
python observerclient.py -s localhost -p 8080
```

Los clientes aceptan `-v` para habilitar mensajes de depuración. El cliente
Observer permite configurar el intervalo de reintento con `--retry-interval`.

## Pruebas y controles

```powershell
python -m pytest --cov=tpfi --cov-branch --cov-report=term-missing
ruff check .
black --check .
mypy src\tpfi singletonclient.py observerclient.py singletonproxyobserver.py
pyright src\tpfi singletonclient.py observerclient.py singletonproxyobserver.py
bandit -q -r src\tpfi singletonclient.py observerclient.py singletonproxyobserver.py
```

La suite automatizada cubre flujos de aceptación, auditoría, errores de
validación, caída de conexión, inicio duplicado del servidor y los patrones
Singleton, Proxy y Observer. El umbral configurado para la cobertura es 85%.

Para ver el camino feliz paso a paso, la distribución de terminales y los casos
manuales y automatizados, consultar la [guía de ejecución y pruebas](docs/GUIA_EJECUCION_PRUEBAS.md).

## Diagramas y documentación

- El proyecto está organizado con el esqueleto Python generado con CookieCutter:
  paquete en `src/`, ejecutables en la raíz y pruebas separadas.
- Diagramas UML en `docs/diagrams/`.
- Documentación API generada con pdoc: `pdoc tpfi -o docs/api`.
- Requisitos del trabajo y prompts usados: `CONTEXT.md`.
- Historial de cambios: `CHANGELOG.md`.

El workflow de GitHub Actions ejecuta controles y pruebas y publica la
documentación generada como artefacto de cada ejecución exitosa.

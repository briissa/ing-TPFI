# TP1-IS2-BRI

Implementación en Python del trabajo práctico final integrador de Ingeniería de
Software II. El sistema ofrece acceso a `CorporateData` mediante un servidor TCP,
usa DynamoDB para persistir datos y auditoría, y aplica los patrones Singleton,
Proxy y Observer.

## Requisitos

- Python 3.10 o superior.
- Tablas DynamoDB `CorporateData` y `CorporateLog` creadas previamente.
- Credenciales y región de AWS configuradas para boto3 al ejecutar el servidor
  o las pruebas.

El servidor usa DynamoDB siempre. La suite automatizada crea tablas efímeras
con nombres únicos en la cuenta AWS configurada y las elimina al finalizar;
requiere permisos para crear, consultar, escribir y eliminar tablas.

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

Después de instalar el proyecto con `python -m pip install -e .`, se pueden
ejecutar operaciones desde otra terminal sin crear archivos JSON:

```powershell
singleton-set --id ID-DE-PRUEBA --cp 3260 --sede FCyT
singleton-get --id ID-DE-PRUEBA
singleton-list
```

`singleton-set` crea o actualiza el registro en DynamoDB; usá un ID adecuado
para evitar modificar datos existentes. Los comandos aceptan `-s` y `-p` para
indicar el servidor y puerto. El modo anterior con `singletonclient.py -i
archivo.json` sigue disponible.

Suscribirse a cambios:

```powershell
python observerclient.py -s localhost -p 8080
```

Los programas aceptan `-v` para mostrar eventos de depuración de la aplicación.
Los detalles HTTP internos del SDK de AWS se mantienen ocultos. El servidor
muestra operaciones `GET`, `SET`, `LIST` y notificaciones sin volcar datos
corporativos completos. El cliente Observer permite configurar el intervalo
de reintento con `--retry-interval`.

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
documentación generada como artefacto de cada ejecución exitosa. Para ejecutar
las pruebas de integración allí, configurar los secretos AWS y la variable
`RUN_AWS_INTEGRATION_TESTS=true`; sin esa configuración, CI omite pytest.

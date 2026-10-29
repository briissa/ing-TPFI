# Guía de ejecución y pruebas

Esta guía explica cómo levantar el sistema en Windows PowerShell, qué proceso
corre en cada terminal y cómo ejecutar el flujo principal y los casos de prueba.

## Componentes del proyecto

- **Servidor TCP:** `singletonproxyobserver.py` (usa la implementación de
  `src\tpfi\server.py`). Escucha en el puerto `8080` por defecto.
- **Cliente de operaciones:** `singletonclient.py` (implementado en
  `src\tpfi\singleton_client.py`). Envía operaciones `set`, `get` y `list`.
- **Cliente Observer:** `observerclient.py` (implementado en
  `src\tpfi\observer_client.py`). Mantiene una conexión abierta para recibir
  avisos de cambios.
- **Datos de ejemplo:** `examples\set.json`, `examples\get.json` y
  `examples\list.json`.
- **Pruebas automatizadas:** `tests\test_aceptacion.py` y `tests\test_humo.py`.

Los clientes se conectan a `localhost:8080`; el puerto debe coincidir con el
indicado al iniciar el servidor. El servidor usa DynamoDB si no se configura
otra cosa. Para probar sin AWS, ejecutar el servidor con
`TPFI_USE_MEMORY=1`. En ese modo, los datos se guardan en memoria y se pierden
al detener el servidor.

## Preparación

Abrir PowerShell en la carpeta raíz del proyecto:

```powershell
Set-Location C:\Users\Briisa\Desktop\TPFI-IS2-BRI
.\.venv\Scripts\Activate.ps1
```

Si todavía no se instaló el entorno, hacerlo una sola vez:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
```

En los ejemplos siguientes se supone que cada terminal está abierta en la raíz
del proyecto y que el entorno virtual está activado.

## Camino feliz: iniciar y usar el sistema

Usar al menos dos terminales. Para probar Observer, abrir una tercera.

### Terminal 1 — servidor

```powershell
$env:TPFI_USE_MEMORY = "1"
python singletonproxyobserver.py -p 8080 -v
```

Dejar esta terminal abierta. El servidor atiende las solicitudes hasta que se
presione `Ctrl+C`. `-v` activa mensajes de depuración; puede omitirse.

### Terminal 2 — cliente de operaciones

Crear o actualizar un registro:

```powershell
python singletonclient.py -i examples\set.json -s localhost -p 8080
```

La respuesta debe ser un objeto JSON del registro. Su identificador será
`UADER-FCyT-IS2`. Leer ese registro:

```powershell
python singletonclient.py -i examples\get.json -s localhost -p 8080
```

La respuesta debe contener el mismo registro. Listar todos los registros:

```powershell
python singletonclient.py -i examples\list.json -s localhost -p 8080
```

La respuesta debe ser una lista que incluya `UADER-FCyT-IS2`.

### Terminal 3 — Observer (opcional)

Iniciar el Observer antes de ejecutar otro `set`:

```powershell
python observerclient.py -s localhost -p 8080 -v
```

Dejarlo conectado y, desde la Terminal 2, repetir la operación `set`:

```powershell
python singletonclient.py -i examples\set.json -s localhost -p 8080
```

El Observer debe imprimir un JSON con `"ACTION": "change"` y los datos del
registro actualizado. Detenerlo con `Ctrl+C`.

## Casos manuales de error

Para cada caso, el servidor debe seguir corriendo en la Terminal 1.

| Caso | Qué hacer | Resultado esperado |
|---|---|---|
| Identificador inexistente | Ejecutar `python -m pytest -v tests\test_aceptacion.py -k rechaza_solicitudes_invalidas` | La prueba confirma que el servidor responde `{"Error": "Not found: missing"}` y rechaza pedidos inválidos. |
| Pedido inválido desde el cliente | Ejecutar `python -m pytest -v tests\test_aceptacion.py -k cliente_singleton_validacion_conexion_y_cli` | Se verifican acciones desconocidas, falta de `ID` o campos de `set`, archivo JSON inválido y respuesta del CLI con error. |
| Puerto ocupado | En una terminal adicional, ejecutar `$env:TPFI_USE_MEMORY = "1"; python singletonproxyobserver.py -p 8080` | El segundo servidor no puede abrir el puerto y termina con un error de inicio. |
| Servidor apagado | Detener el servidor con `Ctrl+C` y, desde otra terminal, ejecutar `python singletonclient.py -i examples\get.json -s localhost -p 8080` | El cliente informa que no pudo conectarse y termina con código de error. |
| Observer y notificaciones | Ejecutar `python -m pytest -v tests\test_aceptacion.py tests\test_humo.py -k "observador or suscripcion"` | Se comprueba la suscripción, la recepción de cambios y el comportamiento ante desconexiones. |

Las pruebas con `pytest` inician sus propios servidores locales y usan tablas en
memoria; no necesitan que el servidor manual esté encendido. Los casos que
envían solicitudes directamente al servidor verifican, entre otros, UUID
faltante, acción desconocida, ID faltante, `set` sin campos y solicitudes que
no son objetos JSON.

## Suite automatizada local

La suite automatizada no usa las tablas AWS: los fixtures de aceptación y humo
fijan `TPFI_USE_MEMORY=1`; además, una prueba del adaptador DynamoDB usa tablas
simuladas. Por eso se puede ejecutar sin credenciales y no valida conectividad,
permisos ni el esquema real de AWS.

Desde la raíz del proyecto:

```powershell
python -m pytest -v
```

Para ejecutar la suite con cobertura de ramas y el umbral configurado:

```powershell
python -m pytest --cov=tpfi --cov-branch --cov-report=term-missing
```

La suite también puede ejecutarse por áreas:

```powershell
# Acciones, auditoría, validaciones y puerto duplicado
python -m pytest -v tests\test_aceptacion.py -k "acciones_y_auditoria or rechaza"

# Proxy, Singleton, almacenamiento y paginación
python -m pytest -v tests\test_aceptacion.py -k "proxy or almacenamiento"

# Protocolo JSON, CLI, conexión y argumentos del servidor
python -m pytest -v tests\test_aceptacion.py -k "protocolo or cliente or servidor_argumentos"
```

Controles adicionales del proyecto:

```powershell
ruff check .
black --check .
mypy src\tpfi singletonclient.py observerclient.py singletonproxyobserver.py
pyright src\tpfi singletonclient.py observerclient.py singletonproxyobserver.py
bandit -q -r src\tpfi singletonclient.py observerclient.py singletonproxyobserver.py
```

## Prueba de integración real con AWS

Esta sección sí conecta con DynamoDB. El servidor escribe en `CorporateData` y
agrega registros a `CorporateLog`; las operaciones de prueba no se limpian
automáticamente. Usar una cuenta y tablas autorizadas para pruebas, no datos de
producción. El `ID` generado abajo evita sobrescribir un registro existente,
pero el registro y sus auditorías quedarán en las tablas.

### 1. Configurar y verificar la cuenta

En PowerShell, configurar las credenciales de forma local. No pegar claves
secretas en comandos, archivos del repositorio ni en el chat. Por ejemplo, con
un perfil ya configurado:

```powershell
$env:AWS_PROFILE = "mi-perfil-de-pruebas"
$env:AWS_DEFAULT_REGION = "us-east-1"
aws sts get-caller-identity
```

Reemplazar `mi-perfil-de-pruebas` y `us-east-1` por el perfil y región
autorizados. `get-caller-identity` debe devolver la cuenta esperada. Verificar
que ambas tablas existan y estén activas:

```powershell
aws dynamodb describe-table --table-name CorporateData --query "Table.TableStatus" --output text
aws dynamodb describe-table --table-name CorporateLog --query "Table.TableStatus" --output text
```

Ambos comandos deben mostrar `ACTIVE`. Confirmar también que la clave de
partición de cada tabla sea de tipo string y se llame `id`, ya que el código
consulta y escribe con esa clave:

```powershell
aws dynamodb describe-table --table-name CorporateData --query "Table.KeySchema" --output table
aws dynamodb describe-table --table-name CorporateLog --query "Table.KeySchema" --output table
```

### 2. Iniciar el servidor conectado a AWS

En la Terminal 1, con el perfil y región configurados:

```powershell
Remove-Item Env:TPFI_USE_MEMORY -ErrorAction SilentlyContinue
python singletonproxyobserver.py -p 8080 -v
```

No establecer `TPFI_USE_MEMORY=1` en esta terminal. El servidor usa
`boto3.resource("dynamodb")` y las tablas `CorporateData` y `CorporateLog`.
Dejarlo abierto mientras se hacen las pruebas. Si aparece un error de
credenciales, región, permisos o tabla, resolverlo antes de seguir.

### 3. Crear solicitudes con un ID único

En la Terminal 2, generar archivos temporales de solicitudes. Los ejemplos usan
solo caracteres ASCII para que funcionen también con Windows PowerShell 5:

```powershell
$testId = "TPFI-AWS-" + [guid]::NewGuid().ToString("N")
$setFile = Join-Path $env:TEMP "tpfi-aws-set.json"
$getFile = Join-Path $env:TEMP "tpfi-aws-get.json"
$listFile = Join-Path $env:TEMP "tpfi-aws-list.json"

@{ UUID = "aws-integration-test"; ACTION = "set"; ID = $testId; cp = "0000"; sede = "AWS-TEST" } |
    ConvertTo-Json |
    Set-Content -Encoding ASCII $setFile
@{ UUID = "aws-integration-test"; ACTION = "get"; ID = $testId } |
    ConvertTo-Json |
    Set-Content -Encoding ASCII $getFile
@{ UUID = "aws-integration-test"; ACTION = "list" } |
    ConvertTo-Json |
    Set-Content -Encoding ASCII $listFile

Write-Output "ID de prueba: $testId"
```

Guardar el ID mostrado si se va a verificar la tabla manualmente.

### 4. Ejecutar el camino feliz contra AWS

Desde la Terminal 2:

```powershell
python singletonclient.py -i $setFile -s localhost -p 8080
python singletonclient.py -i $getFile -s localhost -p 8080
python singletonclient.py -i $listFile -s localhost -p 8080
```

Resultados esperados:

1. `set` devuelve el registro con el mismo `id`, `cp` igual a `0000` y `sede`
   igual a `AWS-TEST`.
2. `get` devuelve el registro creado.
3. `list` devuelve una lista que contiene ese registro. La tabla puede contener
   también otros registros de la cuenta.

Verificar en AWS que se escribió el registro, desde la misma Terminal 2:

```powershell
$key = @{ id = @{ S = $testId } } | ConvertTo-Json -Compress
aws dynamodb get-item --table-name CorporateData --key $key
```

Las operaciones también agregan eventos de auditoría a `CorporateLog`. La
política IAM debe permitir las operaciones necesarias sobre ambas tablas
(lectura, escritura y escaneo según la operación ejecutada).

### 5. Probar Observer contra AWS

En una Terminal 3, iniciar el Observer:

```powershell
python observerclient.py -s localhost -p 8080 -v
```

Con el Observer conectado, repetir el `set` desde la Terminal 2:

```powershell
python singletonclient.py -i $setFile -s localhost -p 8080
```

La Terminal 3 debe mostrar una notificación `"ACTION": "change"`. Detener el
Observer y el servidor con `Ctrl+C` cuando terminen las pruebas.

### 6. Casos negativos e interpretación

- **ID inexistente:** crear un JSON de `get` con un ID aleatorio que no se haya
  usado. El cliente debe recibir `{"Error": "Not found: ..."}`. La lectura se
  audita en `CorporateLog`.
- **Error de conexión:** detener el servidor y ejecutar una operación desde el
  cliente. Debe informar que no pudo conectarse; no se escribe en DynamoDB.
- **Puerto ocupado:** mientras el servidor está activo, intentar iniciar otro
  servidor en el mismo puerto. El segundo debe fallar al hacer bind; no ejecuta
  operaciones de datos.
- **Validaciones de JSON y argumentos:** ejecutarlas con los comandos de la
  suite local. Estas pruebas no son solicitudes a AWS.
- **Permisos insuficientes o tablas inexistentes:** no provocarlos en una cuenta
  compartida. Validar permisos de forma controlada en una cuenta de prueba.

## Alcance de las pruebas contra AWS

El camino feliz, la persistencia, la auditoría y Observer de esta guía son
pruebas de integración reales con AWS. Ejecutar `pytest` sirve para validar la
lógica y los casos automatizados localmente, pero **no** lo convierte en una
prueba contra AWS, aun si `AWS_PROFILE` está configurado. No ejecutar toda la
suite contra tablas compartidas esperando que sus datos se limpien: el código
no ofrece limpieza de registros y la suite está diseñada para aislarse en
memoria o usar dobles de prueba.

# Algoritmo de recomendación (sin IA)

Motor de recomendación por **probabilidad conjunta**, autónomo y sin dependencias
externas. No usa IA, ni red, ni credenciales, ni modelos: sólo matemática y texto.
Se puede integrar en cualquier proyecto (Python 3.9+).

> Esta carpeta es independiente del backend de YUSBO. Es código portable de
> referencia: no se sube al repo del backend.

## Archivos

- `recomendador.py` — el motor (`Recomendador`, almacenes, utilidades).
- `main.py` — demo/plantilla de integración. Ejecuta `python main.py`.

## Cómo funciona

1. Cada acción del usuario es un **evento con peso y signo** (`like`, `dwell`,
   `no_me_interesa`, ...). Los eventos se **atenúan con el tiempo**.
2. Esos eventos forman un **vector de perfil**: categorías + palabras clave.
   Los intereses declarados también cuentan.
3. Cada publicación pasa dos filtros:
   - **Filtro 1 (categoría):** sólo entran categorías con probabilidad suficiente.
   - **Filtro 2 (palabras clave):** la coincidencia de términos debe superar un umbral.
4. La publicación recibe un **peso = probabilidad conjunta en `[0, 1]`**, afinado
   por calidad, recencia y penalización por lo ya visto. Se devuelve ordenado y
   diversificado por categoría. Si nada pasa los filtros, hay un "respaldo" por
   novedad/calidad (cold start nunca queda vacío).

## Uso rápido

```python
from recomendador import Recomendador

motor = Recomendador()

motor.agregar_publicacion({
    "id": "p1", "categoria": "ganado",
    "titulo": "Vaca lechera Holstein",
    "descripcion": "Alta produccion, buena salud.",
    "ubicacion": "Sonora",
    "likes": 4, "vistas": 30, "creado_en": 1700000000,
})

motor.registrar("ana@mail.com", "p1", "like")            # +2.0
motor.registrar("ana@mail.com", "p1", "dwell", 1.5)      # tiempo/30
motor.registrar("ana@mail.com", "p2", "no_me_interesa")  # -4.0

feed = motor.recomendar("ana@mail.com", limite=10, intereses=["ganado"])
for item in feed:
    print(item["peso"], item["titulo"], item["categoria"], item["razon"])
```

### Métodos del motor

| Método | Para qué |
| --- | --- |
| `agregar_publicacion(post)` | Añade o reemplaza una publicación. |
| `eliminar_publicacion(post_id)` | Quita una publicación y reindexa. |
| `registrar(usuario, post_id, evento, cantidad=1.0)` | Guarda un evento del usuario. |
| `olvidar(usuario, post_id=None)` | Borra el historial de un usuario (o de un post). |
| `recomendar(usuario="", limite=10, intereses=None)` | Devuelve la lista ordenada. |

Cada resultado es un dict con `id`, `titulo`, `categoria`, `peso` y `razon`.

## Eventos y pesos (`PESOS_EVENTO`)

| Evento | Peso | Tipo |
| --- | --- | --- |
| `comentario` | +3.0 | explícito |
| `compartir` | +2.5 | explícito |
| `guardar` | +3.0 | explícito |
| `like` | +2.0 | explícito |
| `no_me_interesa` | -4.0 | explícito |
| `dm` | +4.0 | implícito |
| `abrir` | +0.75 | implícito |
| `expandir` | +0.5 | implícito |
| `dwell` | +1.0 | implícito (escala `min(segundos/30, 2)`) |
| `skip` | -0.5 | implícito |

Un interés declarado suma `PESO_INTERES_DECLARADO` (+5.0).

## Campos aceptados

El motor acepta claves en español o inglés:

| Español | Inglés |
| --- | --- |
| `titulo` | `title` |
| `categoria` | `category` |
| `descripcion` | `description` |
| `ubicacion` | `location` |
| `creado_en` | `created_at` |

`likes` y `vistas`/`views` se usan para calidad; si faltan, valen 0.

## Persistencia (opcional)

Por defecto todo vive en memoria. Para persistir:

```python
from recomendador import Recomendador, AlmacenJSON

motor = Recomendador(almacen=AlmacenJSON("recomendador.json"))
```

También puedes pasar `publicaciones=` y `interacciones=` como semilla inicial.

## Configuración

Todos los parámetros están arriba de `recomendador.py`:

- `PESO_INTERES_DECLARADO`, `VIDA_MEDIA_DIAS` — decaimiento temporal.
- `ALPHA`, `TAU_CATEGORIA`, `TAU_TERMINO` — probabilidad y umbrales de filtrado.
- `DIAS_RECENCIA`, `TOPE_CATEGORIA`, `MAX_LIMITE` — recencia, diversidad y tope.
- `MIN_TOKEN`, `MAX_TOKENS`, `STOPWORDS` — indexado de texto e IDF.

## Ejecutar la demo

```bash
python main.py
```

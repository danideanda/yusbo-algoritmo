"""main.py — Ejemplo de integración del Recomendador en cualquier proyecto.

Este archivo no forma parte del backend de YUSBO: es una plantilla autónoma
que muestra cómo enchufar el motor `recomendador.py` a los datos que ya tengas.
No contiene credenciales, no hace red y no escribe archivos salvo que uses
explícitamente `AlmacenJSON`.

Ejecuta `python main.py` para ver una demo con datos de ejemplo.
"""

from recomendador import Recomendador, AlmacenJSON, PESOS_EVENTO


# --------------------------------------------------------------------------
# 1) Adaptadores: conecta el motor con TU base de datos
# --------------------------------------------------------------------------
#
# El motor sólo necesita tres cosas:
#   - publicaciones con id, categoría, título, descripción y ubicación;
#   - eventos por usuario (like, dwell, no_me_interesa, ...);
#   - los intereses declarados del usuario (opcional).
#
# Ejemplo genérico (pseudocódigo de integración):
#
#     motor = Recomendador(almacen=AlmacenJSON("recomendador.json"))
#
#     for fila in mi_db.query("SELECT * FROM publicaciones WHERE activa=1"):
#         motor.agregar_publicacion({
#             "id": fila.id,
#             "categoria": fila.categoria,
#             "titulo": fila.titulo,
#             "descripcion": fila.descripcion,
#             "ubicacion": fila.ubicacion,
#             "likes": fila.likes,
#             "vistas": fila.vistas,
#             "creado_en": fila.creado_en,
#         })
#
#     # en el endpoint que recibe la acción del usuario:
#     motor.registrar(usuario, post_id, "like")            # +2.0
#     motor.registrar(usuario, post_id, "dwell", 1.5)      # tiempo/30
#     motor.registrar(usuario, post_id, "no_me_interesa")  # -4.0
#
#     # al pedir recomendaciones:
#     feed = motor.recomendar(usuario, limite=10, intereses=["ganado", "maiz"])
#
# Si renombras los campos, pasa tus propias claves: el motor acepta tanto
# `titulo`/`categoria`/`descripcion`/`ubicacion` como
# `title`/`category`/`description`/`location`.
# Las claves de evento válidas y sus pesos están en PESOS_EVENTO.


def demo() -> None:
    motor = Recomendador()

    publicaciones = [
        {"id": "p1", "categoria": "ganado", "titulo": "Vaca lechera Holstein",
         "descripcion": "Vaca lechera de alta producción, buena salud.", "ubicacion": "Sonora"},
        {"id": "p2", "categoria": "maiz", "titulo": "Maíz amarillo seco",
         "descripcion": "Maíz amarillo para siembra y alimento balanceado.", "ubicacion": "Sinaloa"},
        {"id": "p3", "categoria": "herramientas", "titulo": "Taladro percutor 800W",
         "descripcion": "Taladro percutor profesional, poco uso.", "ubicacion": "Monterrey"},
        {"id": "p4", "categoria": "ganado", "titulo": "Ternero lechero",
         "descripcion": "Ternero holstein criado con leche.", "ubicacion": "Sonora"},
    ]
    for post in publicaciones:
        motor.agregar_publicacion(post)

    usuario = "ana@ejemplo.com"
    motor.registrar(usuario, "p1", "like")
    motor.registrar(usuario, "p4", "dwell", 2.0)
    motor.registrar(usuario, "p2", "no_me_interesa")

    print("Recomendaciones para", usuario)
    for item in motor.recomendar(usuario, limite=10, intereses=["ganado"]):
        print(f"  [{item['peso']:.4f}] {item['titulo']}  ({item['categoria']})  · {item['razon']}")

    print("\nCold start (usuario nuevo):")
    for item in motor.recomendar("nuevo@ejemplo.com", limite=3):
        print(f"  [{item['peso']:.4f}] {item['titulo']}  ({item['categoria']})")

    print("\nEventos válidos:", ", ".join(sorted(PESOS_EVENTO)))


if __name__ == "__main__":
    demo()

"""recomendador.py — Motor de recomendación por probabilidad conjunta (sin IA).

Código limpio, autónomo y sin dependencias externas. No hace red, no lee
credenciales, no ejecuta código de terceros: sólo matemática y texto. Se puede
integrar en cualquier proyecto pasando tus propias publicaciones, los eventos
del usuario y (opcionalmente) un almacén para persistir.

Idea:
  - Cada acción del usuario es un "elemento" con peso y signo.
  - Los elementos se atenúan con el tiempo y forman un vector de perfil
    (categorías + palabras clave).
  - Una publicación pasa el filtro 1 (categoría) y el filtro 2 (palabras clave)
    y luego recibe un peso = probabilidad conjunta en [0, 1].

Uso rápido:
    from recomendador import Recomendador

    motor = Recomendador()
    motor.agregar_publicacion({"id": "p1", "categoria": "ganado",
                               "titulo": "Vaca lechera", "descripcion": "..."})
    motor.registrar("ana@mail.com", "p1", "like")
    motor.recomendar("ana@mail.com", limite=10, intereses=["ganado"])
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import unicodedata
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------
# Configuración (todo ajustable en un solo lugar)
# --------------------------------------------------------------------------

PESOS_EVENTO: Dict[str, float] = {
    # información explícita
    "comentario": 3.0,
    "compartir": 2.5,
    "guardar": 3.0,
    "like": 2.0,
    "no_me_interesa": -4.0,
    # información implícita
    "dm": 4.0,
    "abrir": 0.75,
    "expandir": 0.5,
    "dwell": 1.0,
    "skip": -0.5,
}
PESO_INTERES_DECLARADO = 5.0
VIDA_MEDIA_DIAS = 30.0
ALPHA = 1.0
TAU_CATEGORIA = 0.25
TAU_TERMINO = 0.18
DIAS_RECENCIA = 7.0
TOPE_CATEGORIA = 3
MAX_LIMITE = 20
MIN_TOKEN = 3
MAX_TOKENS = 40

STOPWORDS = frozenset("""
a al algo algunas algunos ante antes aqui asi aun aunque bien cada contra cual
cuando de del desde donde dos el ella ellas ellos en entre era eran es esa esas
ese eso esos esta estaba estado estan este esto estos fue ha hace hacer hasta
hay la las le les lo los mas me mi mis mucho muy nada ni no nos nosotros o os
otra otras otro otros para pero poco por porque que quien se sean segun ser si
sin sobre solo son su sus te tiene tienen todo todos tu tus un una uno unos y ya
vender vendo vendemos venta oferta ofrezco busco busca comprar compro precio
pesos peso soles dolares ubicado ubicacion ubicada zona cerca contacto informes
whatsapp telefono celular llame escriba disponible disponibilidad nuevo nueva
usado usada bueno buena excelente calidad
""".split())

_PALABRA = re.compile(r"[a-z0-9]+")

# --------------------------------------------------------------------------
# Almacenes opcionales (por defecto, memoria)
# --------------------------------------------------------------------------


class AlmacenMemoria:
    """Almacén por defecto: vive sólo mientras exista el objeto."""

    def __init__(self) -> None:
        self._datos: Dict[str, Any] = {}

    def load(self, clave: str) -> Optional[Any]:
        return self._datos.get(clave)

    def save(self, clave: str, valor: Any) -> None:
        self._datos[clave] = valor


class AlmacenJSON:
    """Persistencia simple en un único archivo JSON (opt-in)."""

    def __init__(self, ruta: str) -> None:
        self.ruta = ruta

    def _leer(self) -> Dict[str, Any]:
        try:
            with open(self.ruta, encoding="utf-8") as archivo:
                datos = json.load(archivo)
            return datos if isinstance(datos, dict) else {}
        except (OSError, ValueError):
            return {}

    def load(self, clave: str) -> Optional[Any]:
        return self._leer().get(clave)

    def save(self, clave: str, valor: Any) -> None:
        datos = self._leer()
        datos[clave] = valor
        with open(self.ruta, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False)


# --------------------------------------------------------------------------
# Utilidades de texto (100% estadísticas)
# --------------------------------------------------------------------------


def normalizar_texto(texto: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(ch for ch in texto if not unicodedata.combining(ch)).lower()


def _raiz(palabra: str) -> str:
    if len(palabra) > 4 and palabra.endswith("es"):
        return palabra[:-2]
    if len(palabra) > 3 and palabra.endswith("s"):
        return palabra[:-1]
    return palabra


def tokenizar(texto: Any) -> List[str]:
    tokens: List[str] = []
    for palabra in _PALABRA.findall(normalizar_texto(texto)):
        if len(palabra) < MIN_TOKEN or palabra in STOPWORDS or palabra.isdigit():
            continue
        termino = _raiz(palabra)
        if len(termino) >= MIN_TOKEN:
            tokens.append(termino)
    return tokens


# --------------------------------------------------------------------------
# Motor
# --------------------------------------------------------------------------


class Recomendador:
    def __init__(self, almacen: Optional[Any] = None,
                 publicaciones: Optional[Iterable[Dict[str, Any]]] = None,
                 interacciones: Optional[Dict[str, Any]] = None) -> None:
        self.almacen = almacen if almacen is not None else AlmacenMemoria()
        self.posts: Dict[str, Dict[str, Any]] = {}
        self.eventos: Dict[str, Dict[str, Dict[str, Any]]] = dict(interacciones or {})
        self._df: Dict[str, int] = {}
        self._tokens: Dict[str, Dict[str, float]] = {}

        guardadas = self.almacen.load("posts")
        for post in (publicaciones if publicaciones is not None else (guardadas or [])):
            self.agregar_publicacion(post)
        self.eventos = dict(self.almacen.load("eventos") or self.eventos)

    # ---- publicaciones -------------------------------------------------

    def agregar_publicacion(self, post: Dict[str, Any]) -> None:
        pid = str(post.get("id") or "")
        if not pid:
            return
        if pid in self.posts:
            self._quitar_del_indice(pid)
        self.posts[pid] = dict(post)
        self._tokens[pid] = self._extraer(post)
        for termino in self._tokens[pid]:
            self._df[termino] = self._df.get(termino, 0) + 1
        self._guardar_posts()

    def eliminar_publicacion(self, post_id: str) -> None:
        if self._quitar_del_indice(post_id):
            self.posts.pop(post_id, None)
            self._guardar_posts()

    def _quitar_del_indice(self, post_id: str) -> bool:
        tokens = self._tokens.pop(post_id, None)
        if tokens is None:
            return False
        for termino in tokens:
            self._df[termino] = max(0, self._df.get(termino, 0) - 1)
        return True

    def _guardar_posts(self) -> None:
        self.almacen.save("posts", list(self.posts.values()))

    def _extraer(self, post: Dict[str, Any]) -> Dict[str, float]:
        campos = (
            (tokenizar(post.get("titulo") or post.get("title")), 3.0),
            (tokenizar(post.get("categoria") or post.get("category")), 2.0),
            (tokenizar(post.get("ubicacion") or post.get("location")), 2.0),
            (tokenizar(post.get("descripcion") or post.get("description")), 1.0),
        )
        tf: Dict[str, float] = {}
        for tokens, peso in campos:
            for termino in tokens:
                tf[termino] = tf.get(termino, 0.0) + peso
        return dict(sorted(tf.items(), key=lambda kv: kv[1], reverse=True)[:MAX_TOKENS])

    def idf(self, termino: str) -> float:
        n = max(len(self.posts), 1)
        return math.log((n + 1) / (self._df.get(termino, 0) + 1)) + 1.0

    # ---- señales -------------------------------------------------------

    def registrar(self, usuario: str, post_id: str, evento: str, cantidad: float = 1.0) -> None:
        if not usuario or post_id not in self.posts or evento not in PESOS_EVENTO:
            return
        try:
            cantidad = float(cantidad)
        except (TypeError, ValueError):
            return
        almacen_usuario = self.eventos.setdefault(usuario.lower(), {})
        registro = almacen_usuario.get(post_id) or {"eventos": {}, "ts": time.time()}
        conteos = registro.setdefault("eventos", {})
        conteos[evento] = conteos.get(evento, 0.0) + cantidad
        if conteos[evento] <= 0:
            conteos.pop(evento, None)
        registro["ts"] = time.time()
        if conteos:
            almacen_usuario[post_id] = registro
        else:
            almacen_usuario.pop(post_id, None)
        self.almacen.save("eventos", self.eventos)

    def olvidar(self, usuario: str, post_id: Optional[str] = None) -> None:
        if post_id is None:
            self.eventos.pop(usuario.lower(), None)
        else:
            self.eventos.get(usuario.lower(), {}).pop(post_id, None)
        self.almacen.save("eventos", self.eventos)

    def _perfil(self, usuario: str, intereses: List[str]) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]], bool]:
        categorias: Dict[str, Dict[str, float]] = {}
        terminos: Dict[str, Dict[str, float]] = {}
        hay_datos = False
        for post_id, registro in (self.eventos.get(usuario.lower()) or {}).items():
            post = self.posts.get(post_id)
            if not post:
                continue
            decaimiento = 0.5 ** (max(0.0, time.time() - float(registro.get("ts") or 0.0)) / 86400.0 / VIDA_MEDIA_DIAS)
            neto = 0.0
            for evento, conteo in (registro.get("eventos") or {}).items():
                neto += PESOS_EVENTO.get(evento, 0.0) * float(conteo) * decaimiento
            if neto == 0.0:
                continue
            hay_datos = True
            _sumar(categorias, str(post.get("categoria") or post.get("category") or "otros"), neto)
            tokens = self._tokens.get(post_id) or {}
            total = sum(tokens.values()) or 1.0
            for termino, tf in tokens.items():
                _sumar(terminos, termino, neto * (tf / total))
        for categoria in intereses:
            _sumar(categorias, str(categoria), PESO_INTERES_DECLARADO)
        return categorias, terminos, hay_datos or bool(intereses)

    # ---- recomendación -------------------------------------------------

    def recomendar(self, usuario: str = "", limite: int = 10,
                   intereses: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        limite = max(1, min(int(limite or 10), MAX_LIMITE))
        if not self.posts:
            return []
        intereses = [str(i) for i in (intereses or [])]
        categorias, terminos, hay_perfil = self._perfil(usuario, intereses)

        elegibles: Optional[set] = None
        if hay_perfil:
            elegibles = set(intereses)
            for categoria, fila in categorias.items():
                if fila["pos"] > 0 and _prob(fila["pos"], fila["neg"]) >= TAU_CATEGORIA:
                    elegibles.add(categoria)
        hay_terminos = any(fila["pos"] > 0 for fila in terminos.values())

        puntuadas: List[Dict[str, Any]] = []
        respaldo: List[Dict[str, Any]] = []
        for post_id, post in self.posts.items():
            categoria = str(post.get("categoria") or post.get("category") or "otros")
            aporte, coincidencias = self._aporte_terminos(post_id, terminos)
            pasa_categoria = elegibles is None or categoria in elegibles
            pasa_terminos = (not hay_terminos) or aporte >= TAU_TERMINO

            p_categoria = _prob((categorias.get(categoria) or {}).get("pos", 0.0),
                                (categorias.get(categoria) or {}).get("neg", 0.0))
            peso = (p_categoria
                    * (aporte if hay_terminos else 0.5)
                    * (0.5 + 0.5 * _calidad(post))
                    * (0.5 + 0.5 * _recencia(post))
                    * (1.0 / (1.0 + 0.5 * self._visto(usuario, post_id))))
            entrada = self._entrada(post, peso, _razones(intereses, coincidencias, post, categoria))
            if pasa_categoria and pasa_terminos:
                puntuadas.append(entrada)
            respaldo.append(self._entrada(post, (0.5 + 0.5 * _calidad(post)) * (0.5 + 0.5 * _recencia(post)), []))

        if not puntuadas:
            puntuadas = respaldo
        puntuadas.sort(key=lambda e: (-e["peso"], self._desempate(usuario, e["id"])))
        return _diversificar(puntuadas, limite)

    def _aporte_terminos(self, post_id: str, terminos: Dict[str, Dict[str, float]]) -> Tuple[float, List[str]]:
        tokens = self._tokens.get(post_id) or {}
        if not tokens or not terminos:
            return 0.0, []
        idfs = {t: self.idf(t) for t in tokens}
        max_idf = max(idfs.values()) or 1.0
        positivo = 0.0
        coincidencias: List[str] = []
        for termino in tokens:
            evidencia = terminos.get(termino)
            if not evidencia or evidencia["pos"] <= 0:
                continue
            probabilidad = _prob(evidencia["pos"], evidencia["neg"])
            if probabilidad < TAU_TERMINO:
                continue
            positivo = 1.0 - (1.0 - positivo) * (1.0 - (idfs[termino] / max_idf) * probabilidad)
            coincidencias.append(termino)
        return positivo, coincidencias

    def _visto(self, usuario: str, post_id: str) -> float:
        registro = (self.eventos.get(usuario.lower()) or {}).get(post_id) or {}
        return float(sum((registro.get("eventos") or {}).values()))

    def _entrada(self, post: Dict[str, Any], peso: float, razones: List[str]) -> Dict[str, Any]:
        return {
            "id": post.get("id"),
            "titulo": post.get("titulo") or post.get("title") or "",
            "categoria": post.get("categoria") or post.get("category") or "otros",
            "peso": round(float(peso), 4),
            "razon": ", ".join(razones[:2]) or "novedad para ti",
        }

    @staticmethod
    def _desempate(usuario: str, post_id: Any) -> int:
        return int(hashlib.sha1((usuario + "|" + str(post_id)).encode("utf-8")).hexdigest()[:8], 16)


# --------------------------------------------------------------------------
# funciones auxiliares
# --------------------------------------------------------------------------


def _sumar(destino: Dict[str, Dict[str, float]], clave: str, peso: float) -> None:
    fila = destino.setdefault(clave, {"pos": 0.0, "neg": 0.0})
    if peso >= 0:
        fila["pos"] += peso
    else:
        fila["neg"] += -peso


def _prob(pos: float, neg: float) -> float:
    return (pos + ALPHA) / (pos + neg + 2.0 * ALPHA)


def _calidad(post: Dict[str, Any]) -> float:
    likes = float(post.get("likes") or 0)
    vistas = float(post.get("vistas") or post.get("views") or 0)
    return 1.0 - math.exp(-(likes + 0.3 * vistas) / 10.0)


def _recencia(post: Dict[str, Any]) -> float:
    creado = float(post.get("creado_en") or post.get("created_at") or 0.0)
    edad = max(0.0, time.time() - creado) if creado else DIAS_RECENCIA * 86400.0
    return math.exp(-edad / (DIAS_RECENCIA * 86400.0))


def _razones(intereses: List[str], coincidencias: List[str], post: Dict[str, Any], categoria: str) -> List[str]:
    razones: List[str] = []
    if categoria in intereses:
        razones.append("te interesa " + categoria)
    if coincidencias:
        razones.append("coincide con “" + ", ".join(coincidencias[:2]) + "”")
    if float(post.get("likes") or 0) > 0:
        razones.append("le gusta a la comunidad")
    return razones


def _diversificar(entradas: List[Dict[str, Any]], limite: int) -> List[Dict[str, Any]]:
    resultado: List[Dict[str, Any]] = []
    resto: List[Dict[str, Any]] = []
    ultima, racha = "", 0
    for entrada in entradas:
        categoria = entrada.get("categoria", "otros")
        if categoria == ultima and racha >= TOPE_CATEGORIA:
            resto.append(entrada)
            continue
        ultima, racha = (categoria, racha + 1) if categoria == ultima else (categoria, 1)
        resultado.append(entrada)
        if len(resultado) >= limite:
            break
    if len(resultado) < limite:
        resultado.extend(resto[: limite - len(resultado)])
    return resultado[:limite]

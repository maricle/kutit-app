import math


def metros_corte(cortes) -> float:
    return sum(c["cantidad"] * 2 * (c["alto"] + c["ancho"]) for c in cortes) / 1000


def metros_canto(cortes) -> float:
    return sum(
        c["cantidad"] * (
            (c["alto"] if c["canto_1"] else 0) + (c["alto"] if c["canto_2"] else 0)
            + (c["ancho"] if c["canto_3"] else 0) + (c["ancho"] if c["canto_4"] else 0)
        )
        for c in cortes
    ) / 1000


def cantidad_placas(cortes, ancho_placa: int, largo_placa: int) -> int:
    area_piezas = sum(c["cantidad"] * c["alto"] * c["ancho"] for c in cortes)
    area_placa = ancho_placa * largo_placa
    return math.ceil(area_piezas / area_placa) if area_placa else 0


def _dividir_en_piezas_individuales(cortes):
    """Expande cada línea de corte (que tiene una cantidad) en piezas
    individuales, y les arma una etiqueta legible: si el nombre se repite
    varias veces se numeran (Estante 1, Estante 2...), si es único queda tal
    cual lo escribió el cliente. Guarda también el nombre base (sin
    numerar) para poder agrupar piezas iguales por color más adelante."""
    total_por_nombre = {}
    for c in cortes:
        nombre = (c["descripcion"] or "Pieza").strip() or "Pieza"
        total_por_nombre[nombre] = total_por_nombre.get(nombre, 0) + int(c["cantidad"])

    contador_por_nombre = {}
    piezas = []
    for c in cortes:
        nombre = (c["descripcion"] or "Pieza").strip() or "Pieza"
        for _ in range(int(c["cantidad"])):
            contador_por_nombre[nombre] = contador_por_nombre.get(nombre, 0) + 1
            etiqueta = (
                f"{nombre} {contador_por_nombre[nombre]}"
                if total_por_nombre[nombre] > 1
                else nombre
            )
            piezas.append({
                "etiqueta": etiqueta,
                "nombre_base": nombre,
                "ancho": int(c["ancho"]),
                "alto": int(c["alto"]),
                "rotar": bool(c["rotar"]),
                "canto_1": bool(c["canto_1"]), "canto_2": bool(c["canto_2"]),
                "canto_3": bool(c["canto_3"]), "canto_4": bool(c["canto_4"]),
            })
    return piezas


def _propiedades_dibujo(pieza):
    """Datos de la pieza original (nombre base, medida nominal y cantos)
    que no cambian al colocarla, para que el dibujo (ver
    `generar_previews_png`) pueda agruparla por color y marcar sus cantos
    aunque haya quedado rotada."""
    return {
        "nombre_base": pieza["nombre_base"],
        "ancho_nominal": pieza["ancho"],
        "alto_nominal": pieza["alto"],
        "canto_1": pieza["canto_1"], "canto_2": pieza["canto_2"],
        "canto_3": pieza["canto_3"], "canto_4": pieza["canto_4"],
    }


def _intentar_colocar(placa, pieza, ancho_placa, largo_placa) -> bool:
    opciones = [(pieza["ancho"], pieza["alto"], False)]
    if pieza["rotar"]:
        opciones.append((pieza["alto"], pieza["ancho"], True))

    # 1) ¿entra en el estante (fila) actual de la placa, a continuación de la última pieza?
    for w, h, rotada in opciones:
        if placa["shelf_alto"] > 0 and placa["shelf_x"] + w <= ancho_placa and h <= placa["shelf_alto"]:
            placa["piezas"].append({
                "etiqueta": pieza["etiqueta"], "x": placa["shelf_x"], "y": placa["shelf_y"],
                "ancho": w, "alto": h, "rotada": rotada, **_propiedades_dibujo(pieza),
            })
            placa["shelf_x"] += w
            return True

    # 2) si no entra, ¿abrimos un estante nuevo debajo, dentro de la misma placa?
    for w, h, rotada in opciones:
        nuevo_y = placa["shelf_y"] + placa["shelf_alto"]
        if w <= ancho_placa and nuevo_y + h <= largo_placa:
            placa["shelf_y"] = nuevo_y
            placa["shelf_alto"] = h
            placa["shelf_x"] = w
            placa["piezas"].append({
                "etiqueta": pieza["etiqueta"], "x": 0, "y": nuevo_y,
                "ancho": w, "alto": h, "rotada": rotada, **_propiedades_dibujo(pieza),
            })
            return True

    return False


def calcular_distribucion(cortes, ancho_placa: int, largo_placa: int) -> dict:
    """Distribuye las piezas pedidas dentro de placas de ancho_placa x
    largo_placa mediante shelf packing (next-fit decreasing height): ordena
    las piezas de mayor a menor y las va acomodando en filas ("estantes"),
    abriendo una placa nueva cuando ya no entran más filas. No es un
    optimizador de nesting irregular (eso requeriría un solver dedicado),
    pero da una distribución real y utilizable, sobre la que se puede medir
    aprovechamiento real en vez de estimarlo por área total."""
    piezas = _dividir_en_piezas_individuales(cortes)
    piezas.sort(key=lambda p: max(p["ancho"], p["alto"]), reverse=True)

    placas = []
    for pieza in piezas:
        if placas and _intentar_colocar(placas[-1], pieza, ancho_placa, largo_placa):
            continue
        placas.append({"piezas": [], "shelf_y": 0, "shelf_alto": 0, "shelf_x": 0})
        if not _intentar_colocar(placas[-1], pieza, ancho_placa, largo_placa):
            # la pieza no entra en la placa ni siquiera vacía (más grande que la
            # placa, incluso rotada): se coloca igual en la esquina, marcada
            # como desbordada, para no perderla silenciosamente.
            placas[-1]["piezas"].append({
                "etiqueta": pieza["etiqueta"], "x": 0, "y": 0,
                "ancho": pieza["ancho"], "alto": pieza["alto"], "rotada": False,
                "desborda": True, **_propiedades_dibujo(pieza),
            })
            placas[-1]["shelf_alto"] = pieza["alto"]
            placas[-1]["shelf_x"] = pieza["ancho"]

    area_placa = ancho_placa * largo_placa
    area_total_piezas = sum(p["ancho"] * p["alto"] for placa in placas for p in placa["piezas"])
    area_total_placas = len(placas) * area_placa

    resultado_placas = []
    for placa in placas:
        area_usada = sum(p["ancho"] * p["alto"] for p in placa["piezas"])
        aprovechamiento = round(100 * area_usada / area_placa, 1) if area_placa else 0.0
        resultado_placas.append({
            "ancho": ancho_placa,
            "largo": largo_placa,
            "piezas": placa["piezas"],
            "aprovechamiento": aprovechamiento,
            "sobrante": round(100 - aprovechamiento, 1),
        })

    aprovechamiento_total = round(100 * area_total_piezas / area_total_placas, 1) if area_total_placas else 0.0

    return {
        "num_placas": len(placas),
        "placas": resultado_placas,
        "total_piezas": len(piezas),
        "aprovechamiento": aprovechamiento_total,
        "sobrante": round(100 - aprovechamiento_total, 1),
    }


def generar_previews_png(resultado: dict) -> list[str]:
    """Dibuja cada placa del resultado de `calcular_distribucion` con el
    MISMO código de dibujo que usa el panel interno para el plano de corte
    real (`optimizador.visualizacion.dibujar_placa` + `optimizador.colores`,
    ver kutit spec/spec-optimizador-corte.md) — mismo color por grupo de
    tamaño, mismo estilo de etiqueta, mismas líneas de canto. Solo cambia
    qué algoritmo decidió la posición de cada pieza (acá, el shelf-packing
    propio); el dibujo en sí es idéntico al del formulario interno.

    Devuelve un PNG en base64 por placa, en el mismo orden que
    `resultado["placas"]`."""
    import base64
    import io

    import matplotlib.pyplot as plt

    from optimizador import colores
    from optimizador.modelos import Cantos, Config, ModoPlaca, ModoCanto, Pieza, PiezaColocada, Placa, Resultado
    from optimizador.visualizacion import dibujar_placa

    ESPESOR_CANTO_DIBUJO = 0.45  # solo define el color de la línea (azul); no afecta ninguna medida acá

    placas_obj = []
    for indice, placa in enumerate(resultado["placas"], start=1):
        piezas_colocadas = []
        for p in placa["piezas"]:
            cantos = Cantos(
                l1=ESPESOR_CANTO_DIBUJO if p["canto_1"] else 0.0,
                l2=ESPESOR_CANTO_DIBUJO if p["canto_2"] else 0.0,
                a1=ESPESOR_CANTO_DIBUJO if p["canto_3"] else 0.0,
                a2=ESPESOR_CANTO_DIBUJO if p["canto_4"] else 0.0,
            )
            pieza_obj = Pieza(
                id=p["etiqueta"], descripcion=p["etiqueta"],
                largo_pedido=p["alto_nominal"], ancho_pedido=p["ancho_nominal"],
                cantos=cantos, rotar=True, fila_csv=0,
                largo_corte=p["alto_nominal"], ancho_corte=p["ancho_nominal"],
                largo_final=p["alto_nominal"], ancho_final=p["ancho_nominal"],
                nombre_base=p["nombre_base"],
            )
            # Transpuesto a propósito: el shelf-packing propio ubica las piezas
            # en un sistema (x <= ancho_placa, y <= largo_placa), pero el dibujo
            # de Kutit Adrián asume el eje contrario (x <= largo, y <= ancho —
            # ver el docstring de optimizador/modelos.py). Sin este transpose,
            # las piezas se dibujan fuera del contorno de la placa.
            piezas_colocadas.append(PiezaColocada(
                pieza=pieza_obj, indice_placa=indice,
                x=p["y"], y=p["x"], ancho_x=p["alto"], alto_y=p["ancho"], rotada=p["rotada"],
            ))
        placas_obj.append(Placa(indice=indice, largo=placa["largo"], ancho=placa["ancho"], piezas=piezas_colocadas))

    cfg = Config(
        placa_largo=resultado["placas"][0]["largo"] if resultado["placas"] else 0,
        placa_ancho=resultado["placas"][0]["ancho"] if resultado["placas"] else 0,
        kerf=0, margen=0, modo_placa=ModoPlaca.LISA, modo_canto=ModoCanto.NINGUNO,
        espesor_canto=ESPESOR_CANTO_DIBUJO, canto_umbral=0,
    )
    resultado_obj = Resultado(placas=placas_obj, no_colocadas=[], total_piezas=resultado["total_piezas"], config=cfg)
    colores_grupo = colores.asignar_colores_grupo(resultado_obj)

    imagenes = []
    for placa_obj in placas_obj:
        ancho_fig = 9.0
        alto_fig = max(3.0, ancho_fig * (placa_obj.ancho / placa_obj.largo))
        fig, ax = plt.subplots(figsize=(ancho_fig, alto_fig))
        dibujar_placa(ax, placa_obj, resultado_obj, colores_grupo)
        fig.tight_layout()
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=130, facecolor="white")
        plt.close(fig)
        imagenes.append(base64.b64encode(buffer.getvalue()).decode("ascii"))

    return imagenes

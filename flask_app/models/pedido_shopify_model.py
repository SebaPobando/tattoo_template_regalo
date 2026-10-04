# ==========================================================================
# pedido_shopify_model.py — el registro de compras confirmadas en Shopify
#
# Qué es: cada vez que alguien paga en el checkout de Shopify, un webhook
# («orders/paid», ver controllers/tienda_controller.py) le avisa a esta app
# y el pedido queda guardado acá.
#
# ESTO ES UN REGISTRO, NO UNA BILLETERA. No suma ni descuenta saldo de
# puntos — eso vive en una tabla de movimientos aparte que todavía no
# existe (ver la nota de `transaccion()` en config/mysqlconnection.py). La
# columna `puntos_acreditados_at` de la tabla es el enganche para esa fase
# futura y hasta entonces nadie la toca.
#
# LA COMPRA SE LIGA A UN USUARIO POR CORREO, SIN EXIGIR CUENTA. Alguien
# puede comprar sin haberse registrado nunca en el sitio y el pedido igual
# queda guardado, con `usuario_id` en NULL. Si después esa persona se
# registra con el mismo correo, los pedidos anteriores NO se re-vinculan
# solos — vincular compras viejas por correo automáticamente es la misma
# clase de agujero que ya se cerró en el registro (la prueba C1 de la
# suite), aunque acá el premio sea mucho menor.
# ==========================================================================

import json

from flask_app import DB
from flask_app.config.mysqlconnection import connectToMySQL


class Pedido:

    # ------------------------------------------------------------ escribir

    @staticmethod
    def registrar(datos):
        """
        Guarda el pedido si no estaba. Idempotente a propósito: Shopify
        reintenta un webhook que no contestó 2xx a tiempo, y a veces entrega
        el mismo dos veces aunque sí se haya procesado bien — es su
        política, no un error. `INSERT IGNORE` sobre el UNIQUE de
        `shopify_order_id` hace que procesar el mismo pedido otra vez no
        invente un segundo registro.

        Devuelve True si quedó guardado, False si ya existía.
        """
        insertado = connectToMySQL(DB).query_db("""
            INSERT IGNORE INTO pedidos_shopify
                (shopify_order_id, numero_orden, usuario_id, correo_comprador,
                 nombre_comprador, monto_clp, moneda, items, creado_shopify_at)
            VALUES
                (%(shopify_order_id)s, %(numero_orden)s, %(usuario_id)s,
                 %(correo_comprador)s, %(nombre_comprador)s, %(monto_clp)s,
                 %(moneda)s, %(items)s, %(creado_shopify_at)s);
        """, dict(datos, items=json.dumps(datos.get("items") or [], ensure_ascii=False)))
        return bool(insertado)

    # ------------------------------------------------------- reembolsos

    @staticmethod
    def actualizar_estado(shopify_order_id, estado):
        """
        Cambia el estado de un pedido YA registrado (pagado -> reembolsado
        o reembolso_parcial), avisado por el webhook orders/updated.

        Si el pedido no existe acá —una actualización de una orden que
        nunca pasó por orders/paid, por ejemplo porque el webhook de
        reembolsos se dio de alta después— no hace nada: no inventa una
        fila a partir de una actualización, solo a partir de un pago
        confirmado.

        Devuelve True si encontró y actualizó el pedido, False si no (no
        existía, o ya estaba en ese estado).
        """
        filas = connectToMySQL(DB).query_db("""
            UPDATE pedidos_shopify
               SET estado = %(estado)s,
                   estado_actualizado_at = UTC_TIMESTAMP()
             WHERE shopify_order_id = %(shopify_order_id)s
               AND estado != %(estado)s;
        """, {"shopify_order_id": shopify_order_id, "estado": estado})
        return bool(filas)

    # -------------------------------------------------------------- panel

    @staticmethod
    def recientes(limite=50):
        """Para /admin/pedidos: lo último primero, con el nombre si hay cuenta."""
        filas = connectToMySQL(DB).query_db("""
            SELECT p.*, u.nombre AS usuario_nombre
            FROM pedidos_shopify p
            LEFT JOIN usuarios u ON u.id = p.usuario_id
            ORDER BY p.recibido_at DESC
            LIMIT %(limite)s;
        """, {"limite": int(limite)})
        for f in filas:
            try:
                f["items"] = json.loads(f["items"]) if f.get("items") else []
            except (TypeError, ValueError):
                f["items"] = []
        return filas

    @staticmethod
    def resumen():
        """
        Para la pastilla del panel: cuántos pedidos y cuánto han sumado.

        Lo reembolsado NO suma: un pedido devuelto dejó de ser una venta, y
        contarlo infla el total con plata que ya se fue. Se cuenta igual en
        `total` —el pedido existió— y `reembolsados` dice cuántos quedaron
        fuera de la suma, para que el número de abajo no parezca un error.

        El reembolso PARCIAL sí suma completo: Shopify avisa que hubo una
        devolución, pero este registro no guarda de cuánto fue (ver
        orders/updated en tienda_controller.py). Restar el pedido entero
        sería mentir más que dejarlo.
        """
        filas = connectToMySQL(DB).query_db("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(CASE WHEN estado = 'reembolsado'
                                     THEN 0 ELSE monto_clp END), 0) AS total_clp,
                   COALESCE(SUM(estado = 'reembolsado'), 0) AS reembolsados
            FROM pedidos_shopify;
        """)
        fila = filas[0] if filas else {}
        return {"total": int(fila.get("total") or 0),
                "total_clp": int(fila.get("total_clp") or 0),
                "reembolsados": int(fila.get("reembolsados") or 0)}

    @staticmethod
    def para_dashboard():
        """
        Lo mismo que `para_totales`, mas los items de cada pedido: es lo que
        necesita /admin/ventas para el ranking de productos.

        Va aparte y no como un parametro de `para_totales` porque los items
        son una columna JSON: traerlos cuesta bastante mas que las tres
        columnas sueltas, y el panel de pedidos —que se abre mucho mas
        seguido— no los necesita para sumar.
        """
        filas = connectToMySQL(DB).query_db("""
            SELECT creado_shopify_at, recibido_at, monto_clp, estado, items
            FROM pedidos_shopify;
        """) or []
        for f in filas:
            try:
                f["items"] = json.loads(f["items"]) if f.get("items") else []
            except (TypeError, ValueError):
                f["items"] = []
        return filas

    @staticmethod
    def para_totales():
        """
        Lo mínimo para sumar por período —fecha, monto y estado— de TODOS los
        pedidos, sin los items ni el join con usuarios.

        Existe separado de `recientes()` por una razón concreta: la lista que
        se muestra viene recortada, y si la plata de cada mes saliera de esa
        lista recortada, un mes con más pedidos de los que caben mostraría un
        total más chico que el real. Equivocarse en la plata en silencio es
        el peor modo de fallar que tiene este panel.

        Son filas diminutas: para el volumen de una cafetería, traerlas todas
        y sumarlas en Python sale más barato que enseñarle husos horarios a
        MySQL (la fecha se guarda en UTC y los cortes son en hora de Chile).
        """
        return connectToMySQL(DB).query_db("""
            SELECT creado_shopify_at, recibido_at, monto_clp, estado
            FROM pedidos_shopify;
        """) or []

/* ===========================================================================
   Plantilla Tienda de Tatuaje — Catálogo de la tienda online (RESPALDO)
   ---------------------------------------------------------------------------
   Esto es el PLAN B. Cuando Shopify está configurado, el catálogo real llega
   desde su API y este archivo no se usa. Cuando no lo está —o Shopify no
   contesta— la sección «Tienda» de la portada pinta estas tarjetas, para que
   nunca quede un hueco en la página.

   Los IDs de variante son inventados: con ellos el botón de pagar lleva a un
   carrito vacío. Reemplázalos por los de la tienda real del cliente, o vacía
   PRODUCTOS y saca la sección de la portada si el negocio no vende despachado.

   Cómo se sacan los IDs: en el admin de Shopify, en la URL de cada variante
   del producto.
   =========================================================================== */
window.LP_TIENDA = (function () {
  "use strict";

  var PRODUCTOS = {
    "insumo-ejemplo": {
      nombre: "Insumo con opciones · Ejemplo",
      desc: "Reemplaza este producto por uno real de la tienda.",
      type: "cafe",
      tamanos: [
        { etiqueta: "Caja de 20", clp: 15000,  variantes: {
            entero: "00000000000001", fino: "00000000000002", medio: "00000000000003" } },
        { etiqueta: "Caja de 50", clp: 34000, variantes: {
            entero: "00000000000004", fino: "00000000000005", medio: "00000000000006" } }
      ]
    },
    "accesorio-ejemplo": {
      nombre: "Accesorio · Ejemplo",
      desc: "Un producto de una sola versión: se agrega directo al carrito.",
      type: "acc",
      tamanos: [ { etiqueta: "Único", clp: 12990, variantes: { unico: "00000000000007" } } ]
    }
  };

  var MOLIENDAS = {
    entero: "3 RL",
    fino:   "5 RL",
    medio:  "7 RL"
  };

  function linea(prod, tamano, molienda, qty) {
    var p = PRODUCTOS[prod];
    if (!p) { return null; }
    var t = null;
    for (var i = 0; i < p.tamanos.length; i++) {
      if (p.tamanos[i].etiqueta === tamano) { t = p.tamanos[i]; }
    }
    if (!t) { t = p.tamanos[0]; }
    var variante = t.variantes[molienda] || t.variantes[Object.keys(t.variantes)[0]];
    var opciones = p.type === "acc" ? t.etiqueta
                 : t.etiqueta + " · " + (MOLIENDAS[molienda] || "");
    return { variante: variante, nombre: p.nombre, opciones: opciones,
             clp: t.clp, qty: qty || 1 };
  }

  return { PRODUCTOS: PRODUCTOS, MOLIENDAS: MOLIENDAS, linea: linea };
})();

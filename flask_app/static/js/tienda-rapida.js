/* ===========================================================================
   Plantilla Cafetería — Eleccion rapida desde la tienda de la landing
   ---------------------------------------------------------------------------
   Deja armar el carrito sin entrar a la ficha de cada cafe: el boton
   "Agregar" de la tarjeta abre un modal con tamano, molienda y cantidad.

   Depende de:
     - window.LP_TIENDA   (static/js/tienda-productos.js) — el catalogo
     - window.LPCarrito   (static/js/carrito.js)          — el carrito

   Enganche en el HTML, un solo atributo por tarjeta:

     <button data-lp-rapido="brasil">Agregar</button>

   Los accesorios (type "acc") no tienen nada que elegir, asi que se agregan
   directo y ni siquiera abren el modal. La ficha completa sigue existiendo
   para quien quiera leer la descripcion: la tarjeta entera sigue enlazando
   a producto.html.
   =========================================================================== */
(function (window, document) {
  "use strict";

  var raiz = null, panel = null;
  var elTitulo, elVendor, elClp, elTamanos, elMoliendas, elQty;
  var campoTamano, campoMolienda, btnAgregar;
  var ultimoFoco = null;

  /* Seleccion actual */
  var prod = null, tamano = null, molienda = null;

  function pesos(n) { return "$" + Number(n).toLocaleString("es-CL"); }

  /* ============================== Montaje ============================== */

  function montar() {
    if (raiz) { return; }
    raiz = document.createElement("div");
    raiz.className = "quickpick";
    raiz.id = "lpQuickpick";
    raiz.hidden = true;
    raiz.innerHTML =
      '<div class="quickpick__overlay" data-qp-cerrar></div>' +
      '<div class="quickpick__panel" role="dialog" aria-modal="true" aria-labelledby="qpTitulo">' +
        '<button class="quickpick__close" type="button" data-qp-cerrar aria-label="Cerrar">' +
          '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' +
        '</button>' +
        '<p class="quickpick__vendor" data-qp-vendor></p>' +
        '<h2 class="quickpick__title" id="qpTitulo" data-qp-titulo></h2>' +
        '<p class="quickpick__price">' +
          '<span class="quickpick__clp" data-qp-clp></span>' +
        '</p>' +
        '<div class="quickpick__field" data-qp-campo-tamano>' +
          '<span class="quickpick__label">Opción</span>' +
          '<div class="quickpick__pills" data-qp-tamanos role="radiogroup" aria-label="Opción"></div>' +
        '</div>' +
        '<div class="quickpick__field" data-qp-campo-molienda>' +
          '<span class="quickpick__label">Variante</span>' +
          '<div class="quickpick__pills" data-qp-moliendas role="radiogroup" aria-label="Variante"></div>' +
        '</div>' +
        '<div class="quickpick__field">' +
          '<span class="quickpick__label">Cantidad</span>' +
          '<div class="quickpick__qty">' +
            '<button class="quickpick__step" type="button" data-qp-menos aria-label="Restar uno">&minus;</button>' +
            '<input class="quickpick__qty-input" type="number" value="1" min="1" max="99" inputmode="numeric" data-qp-qty aria-label="Cantidad" />' +
            '<button class="quickpick__step" type="button" data-qp-mas aria-label="Sumar uno">+</button>' +
          '</div>' +
        '</div>' +
        '<button class="btn btn--primary btn--lg btn--block quickpick__submit" type="button" data-qp-agregar>Agregar al carrito</button>' +
        '<a class="quickpick__more" data-qp-ficha href="#">Ver la ficha completa</a>' +
      '</div>';
    document.body.appendChild(raiz);

    panel        = raiz.querySelector(".quickpick__panel");
    elVendor     = raiz.querySelector("[data-qp-vendor]");
    elTitulo     = raiz.querySelector("[data-qp-titulo]");
    elClp        = raiz.querySelector("[data-qp-clp]");
    elTamanos    = raiz.querySelector("[data-qp-tamanos]");
    elMoliendas  = raiz.querySelector("[data-qp-moliendas]");
    elQty        = raiz.querySelector("[data-qp-qty]");
    campoTamano  = raiz.querySelector("[data-qp-campo-tamano]");
    campoMolienda= raiz.querySelector("[data-qp-campo-molienda]");
    btnAgregar   = raiz.querySelector("[data-qp-agregar]");

    raiz.addEventListener("click", function (e) {
      if (e.target.closest("[data-qp-cerrar]")) { cerrar(); }
    });

    raiz.querySelector("[data-qp-menos]").addEventListener("click", function () {
      elQty.value = Math.max(1, (parseInt(elQty.value, 10) || 1) - 1);
    });
    raiz.querySelector("[data-qp-mas]").addEventListener("click", function () {
      elQty.value = Math.min(99, (parseInt(elQty.value, 10) || 1) + 1);
    });

    btnAgregar.addEventListener("click", function () {
      if (!prod || !window.LPCarrito) { return; }
      var qty = Math.min(99, Math.max(1, parseInt(elQty.value, 10) || 1));
      window.LPCarrito.agregar(window.LP_TIENDA.linea(prod, tamano, molienda, qty));
      cerrar();
      window.LPCarrito.abrir();   /* el drawer es la confirmacion visual */
    });

    document.addEventListener("keydown", function (e) {
      if (raiz.hidden) { return; }
      if (e.key === "Escape") { cerrar(); return; }
      if (e.key === "Tab") { atraparFoco(e); }
    });
  }

  function atraparFoco(e) {
    var focos = panel.querySelectorAll('button:not([disabled]), a[href], input:not([type="radio"]), [type="radio"]:checked, [tabindex]:not([tabindex="-1"])');
    if (!focos.length) { return; }
    var primero = focos[0], ultimo = focos[focos.length - 1];
    if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
  }

  /* ============================== Pintado ============================== */

  function precio() {
    var clp = window.LP_TIENDA.precio(prod, tamano);
    elClp.textContent = pesos(clp);
  }

  /* Construye un grupo de pills de radio. `onPick` recibe el valor elegido.
     `sinStock` es una funcion opcional que dice si un valor esta agotado; esa
     pill queda desactivada en vez de desaparecer, para que se vea QUE existe
     y que hoy no hay. */
  function pills(contenedor, nombre, valores, elegido, onPick, sinStock) {
    contenedor.innerHTML = "";
    valores.forEach(function (v, i) {
      var agotado = typeof sinStock === "function" ? sinStock(v) : false;
      var id = nombre + "-" + i;
      var input = document.createElement("input");
      input.type = "radio";
      input.name = nombre;
      input.id = id;
      input.className = "quickpick__radio";
      input.checked = (v === elegido);
      input.disabled = agotado;
      input.addEventListener("change", function () { onPick(v); });

      var label = document.createElement("label");
      label.className = "quickpick__pill" + (agotado ? " quickpick__pill--agotada" : "");
      label.setAttribute("for", id);
      label.textContent = v;      /* textContent: el valor viene de datos */
      if (agotado) { label.title = "Agotado por ahora"; }

      contenedor.appendChild(input);
      contenedor.appendChild(label);
    });
  }

  /* La primera combinacion que SI se puede comprar. Abrir el modal con una
     opcion agotada preseleccionada es peor que no abrirlo: el boton de
     agregar queda muerto sin que se entienda por que. */
  function primeraDisponible(p) {
    var tamanos = window.LP_TIENDA.tamanos(p);
    var moliendas = window.LP_TIENDA.moliendas(p);
    for (var i = 0; i < tamanos.length; i++) {
      for (var j = 0; j < moliendas.length; j++) {
        if (window.LP_TIENDA.disponible(p, tamanos[i], moliendas[j])) {
          return { tamano: tamanos[i], molienda: moliendas[j] };
        }
      }
    }
    return { tamano: tamanos[0], molienda: moliendas[0] };
  }

  /* El boton de agregar sigue a lo elegido: si la combinacion esta agotada,
     no se puede agregar. */
  function refrescarBoton() {
    if (!btnAgregar || !prod) { return; }
    var hay = window.LP_TIENDA.disponible(prod, tamano, molienda);
    btnAgregar.disabled = !hay;
    btnAgregar.textContent = hay ? "Agregar al carrito" : "Agotado por ahora";
  }

  /* ============================== Abrir / cerrar ============================== */

  function abrir(id, disparador) {
    if (!window.LP_TIENDA || !window.LPCarrito) { return; }
    var p = window.LP_TIENDA.get(id);
    if (!p) { return; }

    /* Un accesorio agotado no abre nada ni se agrega: la tarjeta ya lo dice,
       y el boton ni siquiera existe cuando el servidor pinto el agotado. */
    if (p.agotado) { return; }

    /* Un accesorio no tiene nada que elegir: al carrito y listo. */
    if (p.type === "acc") {
      window.LPCarrito.agregar(window.LP_TIENDA.linea(p, null, null, 1));
      window.LPCarrito.abrir();
      return;
    }

    montar();
    prod = p;
    var tamanos = window.LP_TIENDA.tamanos(prod);
    var moliendas = window.LP_TIENDA.moliendas(prod);
    var inicial = primeraDisponible(prod);
    tamano = inicial.tamano;
    molienda = inicial.molienda;
    elQty.value = 1;

    elVendor.textContent = prod.vendor;
    elTitulo.textContent = prod.name;
    raiz.querySelector("[data-qp-ficha]").setAttribute("href", enlaceFicha(id, disparador));

    /* Si el peso ya forma parte del producto y Shopify solo trae molienda,
       "Único" es una clave interna: no es una opción que la persona elija. */
    if (tamanos.length && !(tamanos.length === 1 && tamanos[0] === "Único")) {
      campoTamano.hidden = false;
      /* Un tamano se marca agotado solo si NINGUNA de sus moliendas queda. */
      pills(elTamanos, "qp-tamano", tamanos, tamano, function (v) {
        tamano = v;
        /* Al cambiar de tamano cambia que moliendas hay, asi que se repintan. */
        pills(elMoliendas, "qp-molienda", moliendas, molienda,
              function (m) { molienda = m; refrescarBoton(); },
              function (m) { return !window.LP_TIENDA.disponible(prod, tamano, m); });
        precio();
        refrescarBoton();
      }, function (v) {
        return !moliendas.some(function (m) {
          return window.LP_TIENDA.disponible(prod, v, m);
        });
      });
    } else {
      campoTamano.hidden = true;
    }

    campoMolienda.hidden = false;
    pills(elMoliendas, "qp-molienda", moliendas, molienda,
          function (v) { molienda = v; refrescarBoton(); },
          function (v) { return !window.LP_TIENDA.disponible(prod, tamano, v); });

    precio();
    refrescarBoton();

    ultimoFoco = document.activeElement;
    raiz.hidden = false;
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { raiz.classList.add("quickpick--open"); });
    });
    document.body.classList.add("has-cart-open");
    btnAgregar.focus();
  }

  /* La URL de la ficha la sabe el HTML (Flask usa url_for, Pages usa una ruta
     relativa), asi que la tomamos de la tarjeta en vez de inventarla aca. */
  function enlaceFicha(id, disparador) {
    var tarjeta = disparador ? disparador.closest(".product") : null;
    var a = tarjeta ? tarjeta.querySelector("a[href]") : null;
    return a ? a.getAttribute("href") : "#";
  }

  function cerrar() {
    if (!raiz || raiz.hidden) { return; }
    raiz.classList.remove("quickpick--open");
    document.body.classList.remove("has-cart-open");
    window.setTimeout(function () { raiz.hidden = true; }, 240);
    if (ultimoFoco && ultimoFoco.focus) { ultimoFoco.focus(); }
  }

  /* ============================== Arranque ============================== */

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-lp-rapido]");
    if (!btn) { return; }
    e.preventDefault();
    abrir(btn.getAttribute("data-lp-rapido"), btn);
  });

  window.LPTiendaRapida = { abrir: abrir, cerrar: cerrar };

})(window, document);

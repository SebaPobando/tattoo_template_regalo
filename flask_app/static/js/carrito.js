/* ===========================================================================
   Plantilla Cafetería — Carrito
   ---------------------------------------------------------------------------
   Vanilla JS, sin dependencias, sin build. Funciona igual servido por Flask
   que como archivo estatico en GitHub Pages.

   Modelo mental
   -------------
   El carrito vive SOLO en el navegador del cliente. Guarda que variantes de
   Shopify quiere y cuantas. No calcula despacho, no valida stock y no cobra:
   al apretar "Ir a pagar" arma un cart permalink de Shopify con todas las
   lineas y Shopify se hace cargo del resto.

       https://TIENDA.myshopify.com/cart/VARIANTE:CANTIDAD,VARIANTE:CANTIDAD

   Por eso el precio guardado aca es SOLO para mostrar. La fuente de verdad
   del precio y del stock es Shopify, siempre.

   La clave de cada linea es el ID de variante: tamano y molienda ya vienen
   codificados dentro de esa variante, asi que dos lineas distintas nunca
   pueden colisionar.

   API publica (window.LPCarrito)
   ------------------------------
     agregar({ variante, nombre, opciones, clp, qty })
     quitar(variante)
     fijarCantidad(variante, qty)
     vaciar()
     lineas()      -> copia del arreglo de lineas
     cantidad()    -> total de unidades
     totalCLP()    -> total en pesos (referencial)
     totalLP()     -> total en puntos (CLP / 10)
     urlCheckout({ descuento, irAlCarrito })
     suscribir(fn) -> devuelve una funcion para desuscribirse
     abrir() / cerrar()
   =========================================================================== */
(function (window, document) {
  "use strict";

  var CLAVE = "lp_carrito_v1";   /* subir la version invalida carritos viejos */
  var QTY_MAX = 99;
  var LP_POR_PESO = 10;          /* 1 LP = $10 CLP */

  /* ======================= Estado ======================= */

  var lineas = [];
  var oyentes = [];

  function esVariante(v) {
    return /^[0-9]{6,20}$/.test(String(v));
  }

  function limpiarQty(n) {
    n = parseInt(n, 10);
    if (!isFinite(n) || n < 1) { return 1; }
    return Math.min(n, QTY_MAX);
  }

  /* Normaliza y descarta cualquier cosa que no calce con el esquema. Si el
     usuario tiene basura en localStorage (o un carrito de una version vieja),
     se ignora en vez de reventar la pagina. */
  function normalizar(linea) {
    if (!linea || !esVariante(linea.variante)) { return null; }
    return {
      variante: String(linea.variante),
      nombre: String(linea.nombre || "Producto"),
      opciones: String(linea.opciones || ""),
      clp: Math.max(0, parseInt(linea.clp, 10) || 0),
      qty: limpiarQty(linea.qty)
    };
  }

  function leerStorage() {
    var crudo;
    try { crudo = window.localStorage.getItem(CLAVE); }
    catch (e) { return []; }              /* modo privado / storage bloqueado */
    if (!crudo) { return []; }
    var datos;
    try { datos = JSON.parse(crudo); }
    catch (e) { return []; }
    if (!Array.isArray(datos)) { return []; }
    var salida = [];
    for (var i = 0; i < datos.length; i++) {
      var l = normalizar(datos[i]);
      if (l) { salida.push(l); }
    }
    return salida;
  }

  function guardar() {
    try { window.localStorage.setItem(CLAVE, JSON.stringify(lineas)); }
    catch (e) { /* sin storage el carrito igual funciona, solo no persiste */ }
  }

  function avisar() {
    guardar();
    for (var i = 0; i < oyentes.length; i++) {
      try { oyentes[i](api.lineas()); } catch (e) { /* un oyente roto no rompe al resto */ }
    }
  }

  function indiceDe(variante) {
    for (var i = 0; i < lineas.length; i++) {
      if (lineas[i].variante === String(variante)) { return i; }
    }
    return -1;
  }

  /* ======================= API ======================= */

  var api = {};

  api.agregar = function (item) {
    var linea = normalizar(item);
    if (!linea) { return false; }
    var i = indiceDe(linea.variante);
    if (i === -1) {
      lineas.push(linea);
    } else {
      lineas[i].qty = limpiarQty(lineas[i].qty + linea.qty);
      lineas[i].clp = linea.clp;          /* refresca el precio de vitrina */
    }
    avisar();
    return true;
  };

  api.quitar = function (variante) {
    var i = indiceDe(variante);
    if (i === -1) { return false; }
    lineas.splice(i, 1);
    avisar();
    return true;
  };

  api.fijarCantidad = function (variante, qty) {
    var i = indiceDe(variante);
    if (i === -1) { return false; }
    if (parseInt(qty, 10) < 1) { return api.quitar(variante); }
    lineas[i].qty = limpiarQty(qty);
    avisar();
    return true;
  };

  api.vaciar = function () {
    lineas = [];
    avisar();
  };

  api.lineas = function () {
    return lineas.map(function (l) {
      return { variante: l.variante, nombre: l.nombre, opciones: l.opciones, clp: l.clp, qty: l.qty };
    });
  };

  api.cantidad = function () {
    return lineas.reduce(function (t, l) { return t + l.qty; }, 0);
  };

  api.totalCLP = function () {
    return lineas.reduce(function (t, l) { return t + (l.clp * l.qty); }, 0);
  };

  api.totalLP = function () {
    return Math.round(api.totalCLP() / LP_POR_PESO);
  };

  /* Arma el cart permalink. Por defecto Shopify manda DIRECTO al checkout;
     con irAlCarrito:true muestra primero el carrito de Shopify. */
  api.urlCheckout = function (opts) {
    opts = opts || {};
    var tienda = String(window.SHOPIFY_STORE_URL || "").replace(/\/+$/, "");
    if (!tienda || tienda.indexOf("TU-TIENDA") !== -1) { return null; }
    if (!lineas.length) { return null; }
    var items = lineas.map(function (l) { return l.variante + ":" + l.qty; }).join(",");
    var url = tienda + "/cart/" + items;
    var params = [];
    if (opts.descuento) { params.push("discount=" + encodeURIComponent(opts.descuento)); }
    if (opts.irAlCarrito) { params.push("storefront=true"); }
    return params.length ? url + "?" + params.join("&") : url;
  };

  api.suscribir = function (fn) {
    if (typeof fn !== "function") { return function () {}; }
    oyentes.push(fn);
    fn(api.lineas());
    return function () {
      var i = oyentes.indexOf(fn);
      if (i !== -1) { oyentes.splice(i, 1); }
    };
  };

  /* ======================= Vista: drawer ======================= */

  var raiz = null, panel = null, lista = null, vacio = null;
  var totalCLPEl = null, btnPagar = null, btnVaciar = null, btnSeguir = null;
  var ultimoFoco = null;
  var confirmandoVaciar = false, temporizadorVaciar = null;

  function resetVaciar() {
    window.clearTimeout(temporizadorVaciar);
    confirmandoVaciar = false;
    if (btnVaciar) {
      btnVaciar.textContent = "Vaciar";
      btnVaciar.classList.remove("cart__clear--confirm");
    }
  }

  function pesos(n) { return "$" + Number(n).toLocaleString("es-CL"); }

  /* A donde vuelve "Seguir comprando" cuando la tienda no esta en esta pagina.
     El nav y el pie ya traen el enlace resuelto por Flask (url_for('home')),
     asi que lo reutilizamos en vez de sumar otra constante a config.js. */
  function urlTienda() {
    var a = document.querySelector('a[href$="#tienda"]');
    return a ? a.getAttribute("href") : "/#tienda";
  }

  function montar() {
    if (raiz) { return; }
    raiz = document.createElement("div");
    raiz.className = "cart";
    raiz.id = "lpCarrito";
    raiz.hidden = true;
    raiz.innerHTML =
      '<div class="cart__overlay" data-lp-cerrar></div>' +
      '<aside class="cart__panel" role="dialog" aria-modal="true" aria-labelledby="lpCarritoTitulo">' +
        '<header class="cart__head">' +
          '<h2 class="cart__title" id="lpCarritoTitulo">Tu carrito</h2>' +
          '<div class="cart__head-actions">' +
            '<button class="cart__clear" type="button" data-lp-vaciar hidden>Vaciar</button>' +
            '<button class="cart__close" type="button" data-lp-cerrar aria-label="Cerrar carrito">' +
              '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' +
            '</button>' +
          '</div>' +
        '</header>' +
        '<div class="cart__body">' +
          '<p class="cart__empty" data-lp-vacio>Todavía no agregas nada. Elige tus productos en la tienda y vuelve por acá.</p>' +
          '<ul class="cart__list" data-lp-lista></ul>' +
        '</div>' +
        '<footer class="cart__foot">' +
          '<div class="cart__total">' +
            '<span class="cart__total-label">Total</span>' +
            '<span class="cart__total-values">' +
              '<span class="cart__total-clp" data-lp-total-clp>$0</span>' +
            '</span>' +
          '</div>' +
          '<div class="cart__actions">' +
            '<button class="btn btn--primary btn--lg btn--block cart__checkout" type="button" data-lp-pagar>Ir a pagar</button>' +
            '<button class="cart__continue" type="button" data-lp-seguir>Seguir comprando</button>' +
          '</div>' +
          '<p class="cart__note">El despacho y el pago se completan de forma segura en Shopify.</p>' +
        '</footer>' +
      '</aside>';
    document.body.appendChild(raiz);

    panel = raiz.querySelector(".cart__panel");
    lista = raiz.querySelector("[data-lp-lista]");
    vacio = raiz.querySelector("[data-lp-vacio]");
    totalCLPEl = raiz.querySelector("[data-lp-total-clp]");
    btnPagar = raiz.querySelector("[data-lp-pagar]");
    btnVaciar = raiz.querySelector("[data-lp-vaciar]");
    btnSeguir = raiz.querySelector("[data-lp-seguir]");

    /* Vaciar es destructivo y no tiene deshacer, asi que va en dos pasos.
       No usamos confirm() nativo: bloquea el hilo y se ve como spam del sitio. */
    btnVaciar.addEventListener("click", function(){
      if (!confirmandoVaciar) {
        confirmandoVaciar = true;
        btnVaciar.textContent = "\u00bfSeguro?";
        btnVaciar.classList.add("cart__clear--confirm");
        /* si se arrepiente y no hace nada, vuelve solo */
        window.clearTimeout(temporizadorVaciar);
        temporizadorVaciar = window.setTimeout(resetVaciar, 4000);
        return;
      }
      resetVaciar();
      api.vaciar();
    });

    raiz.addEventListener("click", function (e) {
      if (e.target.closest("[data-lp-cerrar]")) { api.cerrar(); }
    });

    /* Delegacion: las lineas se redibujan enteras, asi que los handlers
       no pueden vivir en cada boton. */
    lista.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-lp-accion]");
      if (!btn) { return; }
      var variante = btn.getAttribute("data-lp-variante");
      var accion = btn.getAttribute("data-lp-accion");
      var actual = 0;
      var ls = api.lineas();
      for (var i = 0; i < ls.length; i++) { if (ls[i].variante === variante) { actual = ls[i].qty; } }
      if (accion === "mas") { api.fijarCantidad(variante, actual + 1); }
      else if (accion === "menos") { api.fijarCantidad(variante, actual - 1); }
      else if (accion === "quitar") { api.quitar(variante); }
    });

    /* "Seguir comprando" cierra el drawer y devuelve a la tienda. En la landing
       la seccion esta en la misma pagina; en las demas hay que navegar. */
    btnSeguir.addEventListener("click", function () {
      var seccion = document.getElementById("tienda");
      api.cerrar();
      if (seccion) {
        /* sin behavior explicito: respeta el scroll-behavior y el
           scroll-padding-top del CSS, y tambien prefers-reduced-motion */
        seccion.scrollIntoView();
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, "", "#tienda");
        }
        return;
      }
      window.location.href = urlTienda();
    });

    btnPagar.addEventListener("click", function () {
      var url = api.urlCheckout();
      if (!url) {
        alerta("Falta configurar la URL de la tienda Shopify (window.SHOPIFY_STORE_URL).");
        return;
      }
      window.location.href = url;
    });

    document.addEventListener("keydown", function (e) {
      if (raiz.hidden) { return; }
      if (e.key === "Escape") { api.cerrar(); return; }
      if (e.key === "Tab") { atraparFoco(e); }
    });
  }

  function atraparFoco(e) {
    var focos = panel.querySelectorAll('button:not([disabled]), a[href], input, [tabindex]:not([tabindex="-1"])');
    if (!focos.length) { return; }
    var primero = focos[0], ultimo = focos[focos.length - 1];
    if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
  }

  function alerta(msg) {
    var p = raiz.querySelector(".cart__note");
    if (p) { p.textContent = msg; }
  }

  function pintarLineas(ls) {
    if (!raiz) { return; }
    lista.innerHTML = "";
    var hay = ls.length > 0;
    vacio.hidden = hay;
    lista.hidden = !hay;
    btnPagar.disabled = !hay;
    btnVaciar.hidden = !hay;
    if (!hay) { resetVaciar(); }

    ls.forEach(function (l) {
      var li = document.createElement("li");
      li.className = "cart-line";
      li.innerHTML =
        '<div class="cart-line__info">' +
          '<p class="cart-line__name"></p>' +
          '<p class="cart-line__opts"></p>' +
          '<p class="cart-line__price">' +
            '<span class="cart-line__clp"></span>' +
          '</p>' +
        '</div>' +
        '<div class="cart-line__actions">' +
          '<div class="cart-line__qty">' +
            '<button class="cart-line__step" type="button" data-lp-accion="menos" aria-label="Quitar uno">&minus;</button>' +
            '<span class="cart-line__count"></span>' +
            '<button class="cart-line__step" type="button" data-lp-accion="mas" aria-label="Agregar uno">+</button>' +
          '</div>' +
          '<button class="cart-line__remove" type="button" data-lp-accion="quitar">Quitar</button>' +
        '</div>';

      /* textContent en vez de interpolar: el nombre viene de datos, no de codigo */
      li.querySelector(".cart-line__name").textContent = l.nombre;
      var opts = li.querySelector(".cart-line__opts");
      if (l.opciones) { opts.textContent = l.opciones; } else { opts.hidden = true; }
      li.querySelector(".cart-line__clp").textContent = pesos(l.clp * l.qty);
      li.querySelector(".cart-line__count").textContent = l.qty;
      var pasos = li.querySelectorAll("[data-lp-accion]");
      for (var i = 0; i < pasos.length; i++) { pasos[i].setAttribute("data-lp-variante", l.variante); }

      lista.appendChild(li);
    });

    totalCLPEl.textContent = pesos(api.totalCLP());
  }

  /* Badge del header: cualquier elemento con [data-lp-carrito-conteo] */
  function pintarBadges() {
    var n = api.cantidad();
    var badges = document.querySelectorAll("[data-lp-carrito-conteo]");
    for (var i = 0; i < badges.length; i++) {
      badges[i].textContent = n;
      badges[i].hidden = n === 0;
    }
    var botones = document.querySelectorAll("[data-lp-carrito-abrir]");
    for (var j = 0; j < botones.length; j++) {
      botones[j].setAttribute("aria-label", n === 0 ? "Carrito vacio" : "Carrito con " + n + " producto(s)");
    }
  }

  api.abrir = function () {
    montar();
    ultimoFoco = document.activeElement;
    raiz.hidden = false;
    /* doble rAF: el navegador necesita pintar el estado inicial antes de animar */
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { raiz.classList.add("cart--open"); });
    });
    document.body.classList.add("has-cart-open");
    var foco = panel.querySelector(".cart__close");
    if (foco) { foco.focus(); }
  };

  api.cerrar = function () {
    if (!raiz || raiz.hidden) { return; }
    resetVaciar();
    raiz.classList.remove("cart--open");
    document.body.classList.remove("has-cart-open");
    var fin = function () { raiz.hidden = true; };
    window.setTimeout(fin, 260);
    if (ultimoFoco && ultimoFoco.focus) { ultimoFoco.focus(); }
  };

  /* ======================= Arranque ======================= */

  function iniciar() {
    lineas = leerStorage();
    montar();

    api.suscribir(function (ls) { pintarLineas(ls); pintarBadges(); });

    document.addEventListener("click", function (e) {
      var abrir = e.target.closest("[data-lp-carrito-abrir]");
      if (abrir) { e.preventDefault(); api.abrir(); return; }

      /* Agregado rapido desde una tarjeta: variante unica, sin opciones */
      var rapido = e.target.closest("[data-lp-agregar]");
      if (rapido) {
        e.preventDefault();
        api.agregar({
          variante: rapido.getAttribute("data-lp-agregar"),
          nombre: rapido.getAttribute("data-lp-nombre"),
          opciones: rapido.getAttribute("data-lp-opciones") || "",
          clp: rapido.getAttribute("data-lp-clp"),
          qty: rapido.getAttribute("data-lp-qty") || 1
        });
        api.abrir();
      }
    });

    /* Otra pestana del mismo sitio cambio el carrito: sincronizar */
    window.addEventListener("storage", function (e) {
      if (e.key !== CLAVE) { return; }
      lineas = leerStorage();
      pintarLineas(api.lineas());
      pintarBadges();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

  window.LPCarrito = api;

})(window, document);

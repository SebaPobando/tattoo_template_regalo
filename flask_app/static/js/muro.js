/* ===========================================================================
   Plantilla Cafetería — Muro de deseos
   ---------------------------------------------------------------------------
   Hace dos cosas, y las dos son opcionales: si este archivo no cargara, el
   muro se seguiria viendo y el formulario seguiria enviando.

     1. Refresca la seccion #muro de la landing contra /api/v1/muro.
     2. Cuenta los caracteres que quedan en el textarea.

   Por que refrescar algo que el servidor ya pinto:
     - El muro esta moderado. Un mensaje que el admin rechaza tiene que
       desaparecer de la portada, y la portada puede quedar cacheada (por el
       navegador, o por Pages el dia que vuelva ahi).
     - El dia que la landing vuelva a GitHub Pages no va a haber servidor que
       la pinte: este fetch pasa a ser la unica fuente y lo que quedo en el
       HTML es el respaldo.

   Si la API falla NO se toca nada: lo que el servidor dejo en el HTML se
   queda. Un muro de hace un rato es mejor que una seccion en blanco.
   =========================================================================== */
(function (window, document) {
  "use strict";

  /* El limite lo pone el servidor en data-muro-limite y de ahi lo lee esto,
     asi la cifra vive SOLO en EN_LA_LANDING (muro_controller.py). Si estuviera
     escrita aca tambien, el dia que cambie una se separan y el refresco
     mostraria menos deseos que el primer pintado. */
  var LIMITE_POR_DEFECTO = 6;

  /* ----------------------------------------------------------- el refresco */

  function refrescar() {
    var cont  = document.querySelector("[data-muro]");
    var caja  = document.querySelector("[data-muro-carrusel]");
    var vacio = document.querySelector("[data-muro-vacio]");
    var pie   = document.querySelector("[data-muro-pie]");
    if (!cont) { return; }

    var limite = parseInt(cont.getAttribute("data-muro-limite"), 10) || LIMITE_POR_DEFECTO;

    fetch("/api/v1/muro?limite=" + limite, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      })
      .then(function (lista) {
        if (!Array.isArray(lista)) { throw new Error("respuesta inesperada"); }
        pintar(cont, lista);
        var hay = lista.length > 0;
        /* Se esconde la CAJA, no la pista: los botones viven fuera de la
           pista y esconder solo la pista los dejaria flotando solos. */
        if (caja) { caja.hidden = !hay; } else { cont.hidden = !hay; }
        if (vacio) { vacio.hidden = hay; }
        if (pie)   { pie.hidden = !hay; }
        actualizarFlechas();
      })
      .catch(function (e) {
        /* Silencio a proposito: el HTML del servidor sigue en pantalla. */
        if (window.console && console.debug) {
          console.debug("[muro] no se pudo refrescar, queda lo renderizado:", e.message);
        }
      });
  }

  function pintar(cont, lista) {
    cont.innerHTML = "";
    lista.forEach(function (m) { cont.appendChild(tarjeta(m)); });
  }

  /* Mismo markup que el bloque Jinja de landing.html y de muro.html. Son dos
     implementaciones de la misma tarjeta, igual que pasa con la agenda y con
     la carta: si se toca una, hay que tocar la otra. */
  function tarjeta(m) {
    var el = document.createElement("article");
    el.className = "deseo";
    el.innerHTML =
      '<p class="deseo__texto"></p>' +
      '<div class="deseo__pie">' +
        '<span class="deseo__autor"></span>' +
        '<span class="deseo__fecha"></span>' +
      '</div>';

    /* textContent y nunca innerHTML: este texto lo escribio una persona.
       Con innerHTML, un mensaje con <img onerror=...> se ejecutaria en la
       portada — y el filtro del admin no ayuda, porque en la bandeja el
       mensaje se ve como texto inofensivo. */
    el.querySelector(".deseo__texto").textContent = m.mensaje;
    el.querySelector(".deseo__autor").textContent = m.nickname;
    el.querySelector(".deseo__fecha").textContent = m.cuando;
    return el;
  }

  /* -------------------------------------------------------- el contador */

  function contador() {
    var area = document.querySelector("[data-muro-mensaje]");
    var salida = document.querySelector("[data-muro-contador]");
    if (!area || !salida) { return; }

    /* El tope sale del maxlength del propio campo, que lo escribe Jinja
       desde LARGO_MENSAJE del modelo. Asi el numero vive en un solo lugar:
       cambiarlo en Python lo cambia en la base, en el campo y aca. */
    var tope = parseInt(area.getAttribute("maxlength"), 10) || 280;

    function actualizar() {
      var quedan = tope - area.value.length;
      salida.textContent = quedan + " caracteres";
      salida.classList.toggle("muro-form__contador--tope", quedan <= 20);
    }

    area.addEventListener("input", actualizar);
    actualizar();
  }

  /* ------------------------------------------------------------ carrusel */

  /* El desplazamiento ya lo hace el CSS (overflow-x + scroll-snap): se arrastra
     con el dedo y se recorre con el teclado sin esto. Lo unico que agrega este
     bloque son las flechas para el raton, y por eso empieza oculto y solo se
     muestra si de verdad hay algo que desplazar. */

  var pista, flechas;

  function hayDesborde() {
    /* El margen de 4px evita que un redondeo de subpixel muestre las flechas
       en una pista que no se puede mover ni un pixel. */
    return pista && pista.scrollWidth > pista.clientWidth + 4;
  }

  function actualizarFlechas() {
    if (!pista || !flechas) { return; }
    if (!hayDesborde()) { flechas.hidden = true; return; }
    flechas.hidden = false;

    var maximo = pista.scrollWidth - pista.clientWidth;
    var x = pista.scrollLeft;
    flechas.querySelectorAll("[data-muro-ir]").forEach(function (b) {
      var haciaAtras = parseInt(b.getAttribute("data-muro-ir"), 10) < 0;
      b.disabled = haciaAtras ? x <= 2 : x >= maximo - 2;
    });
  }

  function carrusel() {
    pista = document.querySelector("[data-muro]");
    flechas = document.querySelector("[data-muro-controles]");
    if (!pista || !flechas) { return; }

    var quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    flechas.addEventListener("click", function (e) {
      var boton = e.target.closest("[data-muro-ir]");
      if (!boton) { return; }
      /* Se avanza casi una pantalla y no una tarjeta exacta: el scroll-snap
         del CSS termina de cuadrarlo en el borde de la tarjeta mas cercana,
         asi que no hay que calcular anchos ni margenes a mano. */
      var salto = Math.max(pista.clientWidth * 0.9, 240);
      pista.scrollBy({
        left: salto * parseInt(boton.getAttribute("data-muro-ir"), 10),
        behavior: quieto ? "auto" : "smooth"
      });
    });

    /* El scroll dispara muchisimo; requestAnimationFrame deja una sola
       actualizacion por cuadro en vez de una por evento. */
    var pedido = false;
    function alMoverse() {
      if (pedido) { return; }
      pedido = true;
      window.requestAnimationFrame(function () {
        pedido = false;
        actualizarFlechas();
      });
    }

    pista.addEventListener("scroll", alMoverse, { passive: true });
    window.addEventListener("resize", alMoverse);

    actualizarFlechas();
  }

  function iniciar() {
    carrusel();
    refrescar();
    contador();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

})(window, document);

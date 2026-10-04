/* ===========================================================================
   Plantilla Cafetería — Agenda de la landing
   ---------------------------------------------------------------------------
   La seccion #talleres ya viene pintada desde el servidor. Esto la refresca
   contra /api/v1/agenda.

   Por que refrescar algo que el servidor ya pinto:
     - Los cupos cambian solos cada vez que alguien se inscribe, y la landing
       puede quedar cacheada (por el navegador, o por Pages el dia que vuelva
       ahi). Mostrar "quedan 2 cupos" cuando ya no hay ninguno es peor que no
       mostrar el numero.
     - El dia que la landing vuelva a GitHub Pages no va a haber servidor que
       la pinte: este fetch pasa a ser la unica fuente y lo que quedo en el
       HTML es el respaldo.

   Si la API falla NO se toca nada: lo que el servidor dejo en el HTML se
   queda. Una agenda de hace un rato es mejor que una seccion en blanco.
   =========================================================================== */
(function (window, document) {
  "use strict";

  var URL_API = "/api/v1/agenda?limite=3";
  var URL_AGENDA = "/actividades";

  function iniciar() {
    var cont  = document.querySelector("[data-agenda]");
    var vacio = document.querySelector("[data-agenda-vacio]");
    var pie   = document.querySelector("[data-agenda-pie]");
    if (!cont) { return; }

    /* Una URL de afiche puede vencer o dejar de responder. Si ocurre, no se
       conserva una columna vacia: la informacion recupera ese espacio. */
    var afichesIniciales = cont.querySelectorAll(".evento__afiche");
    for (var i = 0; i < afichesIniciales.length; i++) {
      afichesIniciales[i].addEventListener("error", ocultarAfiche);
    }

    fetch(URL_API, { headers: { Accept: "application/json" } })
      .then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      })
      .then(function (lista) {
        if (!Array.isArray(lista)) { throw new Error("respuesta inesperada"); }
        pintar(cont, lista);
        var hay = lista.length > 0;
        cont.hidden = !hay;
        if (vacio) { vacio.hidden = hay; }
        if (pie)   { pie.hidden = !hay; }
      })
      .catch(function (e) {
        /* Silencio a proposito: el HTML del servidor sigue en pantalla. */
        if (window.console && console.debug) {
          console.debug("[agenda] no se pudo refrescar, queda lo renderizado:", e.message);
        }
      });
  }

  function pintar(cont, lista) {
    cont.innerHTML = "";
    lista.forEach(function (a) {
      cont.appendChild(tarjeta(a));
    });
  }

  function ocultarAfiche(e) {
    e.currentTarget.hidden = true;
  }

  /* Mismo markup que el bloque Jinja de landing.html. Son dos
     implementaciones de la misma tarjeta: si se toca una, hay que tocar la
     otra. */
  function tarjeta(a) {
    var el = document.createElement("a");
    el.className = "evento";
    el.href = a.url || (URL_AGENDA + "/" + a.slug);
    el.innerHTML =
      '<img class="evento__afiche" alt="" loading="lazy" hidden />' +
      '<div class="evento__contenido">' +
        '<div class="evento__fecha">' +
          '<div class="evento__dia"></div>' +
          '<div class="evento__mes"></div>' +
        '</div>' +
        '<div class="evento__cuerpo">' +
          '<h3 class="evento__nombre"></h3>' +
          '<p class="evento__dato" data-cuando></p>' +
          '<p class="evento__dato" data-lugar></p>' +
          '<div class="evento__pie">' +
            '<span class="pastilla pastilla--precio"></span>' +
            '<span class="pastilla" data-cupos></span>' +
          '</div>' +
        '</div>' +
      '</div>';

    /* textContent en todo: los textos vienen de la base, no del codigo. */
    /* El afiche es opcional: sin el, la miniatura se queda oculta y la
       tarjeta se ve igual que siempre. `src` solo se toca si hay algo, para
       no pedirle al navegador una imagen vacia. */
    var afiche = el.querySelector(".evento__afiche");
    if (a.imagen) {
      afiche.addEventListener("error", ocultarAfiche);
      afiche.src = a.imagen;
      afiche.alt = "Afiche de " + a.nombre;
      afiche.hidden = false;
    }

    el.querySelector(".evento__dia").textContent = a.dia;
    el.querySelector(".evento__mes").textContent = a.mes;
    el.querySelector(".evento__nombre").textContent = a.nombre;
    el.querySelector("[data-cuando]").textContent = a.cuando;

    var lugar = el.querySelector("[data-lugar]");
    if (a.lugar) { lugar.textContent = a.lugar; } else { lugar.hidden = true; }

    el.querySelector(".pastilla--precio").textContent = a.precio_fmt;

    var cupos = el.querySelector("[data-cupos]");
    if (a.agotada) {
      cupos.className = "pastilla pastilla--agotada";
      cupos.textContent = "Sin cupos";
    } else if (a.libres <= 3) {
      cupos.className = "pastilla pastilla--pocos";
      cupos.textContent = "Quedan " + a.libres + " cupo" + (a.libres !== 1 ? "s" : "");
    } else {
      cupos.className = "pastilla pastilla--libre";
      cupos.textContent = a.libres + " cupos";
    }

    return el;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

})(window, document);

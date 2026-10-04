/* ===========================================================================
   Plantilla Cafetería — Banner de promocion de la portada
   ---------------------------------------------------------------------------
   El servidor inyecta los SEGUNDOS QUE QUEDAN en data-segundos, no la fecha
   de termino. Contra una fecha absoluta el plazo dependeria del reloj de cada
   visitante: quien lo tenga corrido ve otra cosa, y quien lo atrase se
   extiende la promo solo. Aca el reloj del navegador se usa unicamente para
   medir cuanto ha pasado DESDE que cargo la pagina, que es lo unico para lo
   que sirve.

   De ahi el "vence" local: se calcula una vez al cargar y el contador se
   deriva de el en cada tick. Con un simple `restan -= 1` bastaria con que la
   pestana pasara a segundo plano —donde el navegador frena los timers— para
   que el contador se fuera quedando atras, y al volver mostraria de menos.

   El banner sale siempre al cargar (lo abre el script inline de
   _promo.html). Cerrarlo o esconder la burbuja vale solo para esta visita:
   no se guarda nada en el navegador. Aca solo se cuenta y se responde a los
   clics.
   =========================================================================== */
(function (window, document) {
  "use strict";

  var banner = document.getElementById('lpPromo');
  var burbuja = document.getElementById('lpPromoBurbuja');
  if (!banner) { return; }

  var idPromo = banner.dataset.promo;

  var elDias = banner.querySelector('[data-promo-dias]');
  var elDD = banner.querySelector('[data-promo-dd]');
  var elHH = banner.querySelector('[data-promo-hh]');
  var elMM = banner.querySelector('[data-promo-mm]');
  var elSS = banner.querySelector('[data-promo-ss]');
  var elMini = burbuja ? burbuja.querySelector('[data-promo-mini]') : null;
  var elPlazo = banner.querySelector('[data-promo-plazo]');

  /* SIN data-segundos = promo sin fecha de termino: corre hasta que la
     apaguen. Hay que distinguirlo de un plazo vencido, porque la reaccion
     es la contraria: una promo vencida se retira, una sin plazo se queda.
     Antes esto no existia y el atributo siempre venia; si llegara vacio, el
     parseInt daba NaN y el banner se escondia solo. */
  var sinPlazo = !('segundos' in banner.dataset) || banner.dataset.segundos === '';
  var segundos = parseInt(banner.dataset.segundos, 10);
  if (!sinPlazo && (!isFinite(segundos) || segundos <= 0)) { terminar(); return; }

  var vence = Date.now() + segundos * 1000;
  var tic = null;
  var porScroll = false;   /* la burbuja la abrio el scroll, no la persona */

  function dos(n) { return (n < 10 ? '0' : '') + n; }

  /* ------------------------------------------------------------ contador */

  function pintar() {
    var restan = Math.max(0, Math.round((vence - Date.now()) / 1000));
    var d = Math.floor(restan / 86400);
    var h = Math.floor((restan % 86400) / 3600);
    var m = Math.floor((restan % 3600) / 60);
    var s = restan % 60;

    if (elDias) { elDias.hidden = (d === 0); }
    if (elDD) { elDD.textContent = dos(d); }
    if (elHH) { elHH.textContent = dos(h); }
    if (elMM) { elMM.textContent = dos(m); }
    if (elSS) { elSS.textContent = dos(s); }
    if (elMini) {
      elMini.textContent = (d > 0 ? d + 'd ' : '') + dos(h) + ':' + dos(m) + ':' + dos(s);
    }

    banner.classList.toggle('promo--urgente', restan > 0 && restan < 3600);

    /* El contador va aria-hidden porque cambia cada segundo. Esto es lo que
       si lee un lector de pantalla, y por eso se escribe en palabras. */
    if (elPlazo && restan < 86400) {
      elPlazo.textContent = restan > 3600
        ? 'Quedan ' + h + (h === 1 ? ' hora.' : ' horas.')
        : 'Quedan menos de 60 minutos.';
    }

    if (restan <= 0) { terminar(); }
  }

  function terminar() {
    /* Se retira sola. Un banner clavado en 00:00:00 anunciando algo que ya
       no existe es peor que no haber mostrado nada. */
    if (tic) { window.clearInterval(tic); tic = null; }
    banner.hidden = true;
    if (burbuja) { burbuja.hidden = true; }
  }

  /* -------------------------------------------------------- abrir/cerrar */

  function mostrarBurbuja() {
    if (!burbuja || !burbuja.hidden) { return; }
    burbuja.hidden = false;
    burbuja.classList.add('promo-burbuja--entrando');
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        burbuja.classList.remove('promo-burbuja--entrando');
      });
    });
  }

  function cerrarBanner() {
    banner.hidden = true;
    porScroll = false;
    mostrarBurbuja();
  }

  function abrirBanner() {
    if (burbuja) { burbuja.hidden = true; }
    banner.hidden = false;
    banner.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  var btnCerrar = banner.querySelector('[data-promo-cerrar]');
  if (btnCerrar) { btnCerrar.addEventListener('click', cerrarBanner); }

  if (burbuja) {
    var btnAbrir = burbuja.querySelector('[data-promo-abrir]');
    if (btnAbrir) { btnAbrir.addEventListener('click', abrirBanner); }

    var btnDescartar = burbuja.querySelector('[data-promo-descartar]');
    if (btnDescartar) {
      btnDescartar.addEventListener('click', function (e) {
        e.stopPropagation();
        burbuja.hidden = true;
      });
    }
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !banner.hidden) { cerrarBanner(); }
  });

  /* ------------------------------------------------------------- scroll */

  /* Si el banner se pierde de vista sin que nadie lo cierre, aparece la
     burbuja para que la promo siga disponible. Esto NO se recuerda: bajar por
     la pagina no es una decision sobre la promo, y guardarla dejaria a quien
     solo hizo scroll sin volver a ver el banner nunca mas.

     OJO: el banner NO se esconde aca, solo queda fuera de pantalla. Un
     elemento con display:none no vuelve a disparar el observer, asi que
     esconderlo dejaria la burbuja pegada para siempre aunque la persona
     subiera de nuevo. */
  if (burbuja && 'IntersectionObserver' in window) {
    var vigia = new IntersectionObserver(function (entradas) {
      if (banner.hidden) { return; }   /* lo cerro la persona: manda eso */
      if (!entradas[0].isIntersecting) {
        porScroll = true;
        mostrarBurbuja();
      } else if (porScroll) {
        burbuja.hidden = true;
        porScroll = false;
      }
    }, { threshold: 0 });
    vigia.observe(banner);
  }

  /* El contador solo corre si hay algo que contar. Sin plazo, `vence` seria
     NaN y pintar() escribiria basura en el reloj (o lo daria por vencido).
     La plantilla tampoco pinta el reloj en ese caso, asi que no hay nada
     que actualizar. */
  if (!sinPlazo) {
    pintar();
    tic = window.setInterval(pintar, 1000);

    /* Al volver de segundo plano el navegador pudo saltarse muchos ticks. */
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) { pintar(); }
    });
  }

})(window, document);

/* ===========================================================================
   Plantilla Cafetería — utilidades de front del área de cuenta
   ---------------------------------------------------------------------------
   Se conservaron los formateadores y la validación de RUT chileno (con dígito
   verificador), que son correctos y siguen sirviendo.

   Se ELIMINÓ la sesión falsa en localStorage (lpEnsureSession, lpDemoUser,
   lpSetLoggedIn, lpDemoMovements): la sesión ahora la maneja Flask con cookie,
   y el saldo lo entrega el servidor. Nunca dejes el saldo en el navegador.
   =========================================================================== */

var LP_BIENVENIDA = 3000;


/* --- Formato CLP --- */
function lpCLP(n){ return '$' + Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
function lpPts(n){ return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }

/* --- RUT chileno: máscara + dígito verificador --- */
function lpRutDV(numStr){
  var sum = 0, mul = 2;
  for (var i = numStr.length - 1; i >= 0; i--){
    sum += parseInt(numStr[i], 10) * mul;
    mul = mul < 7 ? mul + 1 : 2;
  }
  var res = 11 - (sum % 11);
  if (res === 11) return '0';
  if (res === 10) return 'K';
  return String(res);
}
function lpFormatRut(raw){
  var clean = raw.replace(/[^0-9kK]/g, '').toUpperCase();
  if (!clean) return '';
  var dv = clean.slice(-1);
  var num = clean.slice(0, -1);
  var withDots = num.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return num ? (withDots + '-' + dv) : dv;
}
function lpValidateRut(formatted){
  var clean = formatted.replace(/[^0-9kK]/g, '').toUpperCase();
  if (clean.length < 2) return false;
  var dv = clean.slice(-1);
  var num = clean.slice(0, -1);
  return lpRutDV(num) === dv;
}
function lpBindRutField(input, hintEl){
  input.addEventListener('input', function(){
    var pos = input.selectionStart;
    input.value = lpFormatRut(input.value);
    if (hintEl) {
      var ok = lpValidateRut(input.value);
      hintEl.textContent = input.value.length > 2 ? (ok ? 'RUT válido.' : 'RUT inválido — revisa el dígito verificador.') : 'Formato chileno con dígito verificador.';
      hintEl.style.color = input.value.length > 2 ? (ok ? 'var(--lp-success)' : 'var(--lp-danger)') : 'var(--text-muted)';
    }
  });
}

/* --- Medidor de fuerza de contraseña --- */
function lpPasswordScore(pw){
  var score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score;
}
function lpBindPasswordStrength(input, barEl, labelEl){
  input.addEventListener('input', function(){
    var score = lpPasswordScore(input.value);
    var pct = input.value ? Math.min(100, (score / 5) * 100) : 0;
    barEl.style.width = pct + '%';
    var labels = ['Muy débil', 'Débil', 'Regular', 'Buena', 'Fuerte', 'Excelente'];
    var colors = ['#B23B2E', '#B23B2E', '#C68A2E', '#C68A2E', '#3C7A4E', '#3C7A4E'];
    barEl.style.background = colors[score];
    labelEl.textContent = input.value ? labels[score] : '';
  });
}

/* --- Movimientos de ejemplo --- */
var LP_BADGE = { earn: ['Ganado', 'badge--earn'], buy: ['Comprado', 'badge--buy'], redeem: ['Canjeado', 'badge--redeem'] };

/* --- Header: estado de cuenta + menú hamburguesa + toggle de sesión demo --- */
function lpInitHeader(){
  var toggle = document.getElementById('navToggle');
  var nav = document.getElementById('nav');
  if (toggle && nav) {
    toggle.addEventListener('click', function(){
      var open = nav.classList.toggle('nav--open');
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
}

// OJO: esto va aparte de lpInitHeader() a propósito. landing.html define
// window.__lpHeaderHandled = true porque trae su propio toggle de la
// hamburguesa, y ese guard saltaba TODO lpInitHeader(). El menú de cuenta se
// bindea en un solo lugar, así que tiene que correr siempre, landing incluida.
function lpInitCuenta(){
  // El menú de cuenta lo renderiza el servidor en _nav.html según la sesión
  // de Flask. Antes se pintaba acá leyendo localStorage.
  var acctTrig = document.getElementById('acctTrigger');
  var acctMenu = document.getElementById('acctMenu');

  function acctCerrar(){
    if (!acctMenu) return;
    acctMenu.classList.remove('acct__menu--open');
    if (acctTrig) acctTrig.setAttribute('aria-expanded', 'false');
  }

  if (acctTrig && acctMenu) {
    acctTrig.addEventListener('click', function(e){
      e.stopPropagation();   // si no, el listener de abajo lo cierra al toque
      var abierto = acctMenu.classList.toggle('acct__menu--open');
      acctTrig.setAttribute('aria-expanded', abierto ? 'true' : 'false');
    });
    // Escape cierra: es un menú, no una página.
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape') acctCerrar();
    });
  }

  document.addEventListener('click', function(e){
    if (acctMenu && acctTrig && !acctTrig.contains(e.target) && !acctMenu.contains(e.target)) acctCerrar();
  });
}
/* El easter egg de Sr. Jengibre: cinco clics en el credito del footer, el
   logo o una mascota y caen galletas. Va en TODAS las instalaciones junto
   con el credito (ver _footer_credito.html); no se quita. */
function lpInitJengibre(){
  var credit = document.getElementById('footerCredit');
  var logo = document.querySelector('.footer__logo');
  var mascots = document.querySelectorAll('.mascot, img[src*="mascotas/"]');
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var clicks = 0, timer = null;
  function registerClick(){
    clicks++;
    clearTimeout(timer);
    timer = setTimeout(function(){ clicks = 0; }, 4000);
    if (clicks < 5) return;
    clicks = 0;
    showJengibre();
  }
  if (credit) credit.addEventListener('click', registerClick);
  if (logo) logo.addEventListener('click', registerClick);
  Array.prototype.forEach.call(mascots, function(m){
    m.style.pointerEvents = 'auto';
    m.style.cursor = 'pointer';
    m.addEventListener('click', registerClick);
  });
  function showJengibre(){
    var rain = document.createElement('div');
    rain.className = 'jengibre-rain';
    document.body.appendChild(rain);
    var gingerSvg = '<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg"><g fill="#b06a35"><circle cx="24" cy="10" r="7"/><rect x="18" y="15" width="12" height="14" rx="6"/><rect x="6" y="16" width="12" height="7" rx="3.5" transform="rotate(-25 6 16)"/><rect x="30" y="16" width="12" height="7" rx="3.5" transform="rotate(25 42 16)"/><rect x="14" y="27" width="9" height="14" rx="4.5" transform="rotate(-12 14 27)"/><rect x="25" y="27" width="9" height="14" rx="4.5" transform="rotate(12 34 27)"/></g><g fill="#fcf8f1"><circle cx="21" cy="9" r="1.6"/><circle cx="27" cy="9" r="1.6"/><path d="M20 13 q4 3 8 0" stroke="#fcf8f1" stroke-width="1.6" fill="none" stroke-linecap="round"/><circle cx="24" cy="19" r="1.3"/><circle cx="24" cy="24" r="1.3"/><path d="M14 18 h20 M14 30 h6 M28 30 h6" stroke="#fcf8f1" stroke-width="1.4" stroke-dasharray="2 2"/></g><circle cx="10" cy="18" r="2" fill="#c23b3b"/><circle cx="38" cy="18" r="2" fill="#c23b3b"/></svg>';
    var count = reduced ? 1 : 16;
    for (var i = 0; i < count; i++){
      var c = document.createElement('span');
      c.className = 'jengibre-cookie';
      c.innerHTML = gingerSvg;
      c.style.cssText = 'position:absolute;top:-8vh;width:30px;height:30px;opacity:0;animation:cookieFall linear forwards;display:block';
      var svgEl = c.querySelector('svg');
      svgEl.setAttribute('width', '30');
      svgEl.setAttribute('height', '30');
      svgEl.style.cssText = 'width:30px;height:30px;display:block';
      c.style.left = (Math.random() * 100) + 'vw';
      c.style.animationDuration = (2.4 + Math.random() * 1.6) + 's';
      c.style.animationDelay = (Math.random() * 0.6) + 's';
      rain.appendChild(c);
    }
    var card = document.createElement('div');
    card.className = 'jengibre-card';
    card.innerHTML = '<strong><span style="display:inline-flex;width:22px;height:22px;vertical-align:-5px;margin-right:4px">' + gingerSvg + '</span>Sr. Jengibre estuvo aquí</strong>Este sitio fue horneado (programado) con cariño.';
    var cardSvg = card.querySelector('svg');
    cardSvg.setAttribute('width', '22');
    cardSvg.setAttribute('height', '22');
    cardSvg.style.cssText = 'width:22px;height:22px;display:block';
    document.body.appendChild(card);
    requestAnimationFrame(function(){ card.classList.add('is-visible'); });
    setTimeout(function(){
      card.classList.remove('is-visible');
      setTimeout(function(){ card.remove(); rain.remove(); }, 350);
    }, 3200);
  }
}
document.addEventListener('DOMContentLoaded', function(){
  if (!window.__lpHeaderHandled) { lpInitHeader(); }
  lpInitCuenta();
  lpInitJengibre();
});

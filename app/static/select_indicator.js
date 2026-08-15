(() => {
  "use strict";

  const STYLE_ID = "crapscraper-select-indicator-style";
  const previous = document.getElementById(STYLE_ID);
  if (previous) previous.remove();

  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    select:not([multiple]) {
      -webkit-appearance: none !important;
      appearance: none !important;
      padding-right: 42px !important;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='10' viewBox='0 0 14 10'%3E%3Ctext x='0' y='9' font-size='11' fill='%23cbd5e1'%3E%E2%96%BC%3C/text%3E%3C/svg%3E") !important;
      background-repeat: no-repeat !important;
      background-position: right 14px center !important;
      background-size: 14px 10px !important;
    }

    select:not([multiple]):disabled {
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='10' viewBox='0 0 14 10'%3E%3Ctext x='0' y='9' font-size='11' fill='%2371717a'%3E%E2%96%BC%3C/text%3E%3C/svg%3E") !important;
    }
  `;
  document.head.appendChild(style);
})();

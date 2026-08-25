(() => {
  "use strict";
  if (window.__crapScraperProcessCreditFreezeGuardInstalled) return;
  window.__crapScraperProcessCreditFreezeGuardInstalled = true;

  // process_history_credits.js observa alterações de childList no documento e
  // também atualiza os próprios contadores com innerHTML. Sem esta proteção,
  // uma escrita idêntica dispara o observer novamente e pode formar um ciclo
  // MutationObserver -> renderCredits -> innerHTML -> MutationObserver.
  const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
  if (!descriptor?.get || !descriptor?.set) return;

  try {
    Object.defineProperty(Element.prototype, "innerHTML", {
      configurable: descriptor.configurable,
      enumerable: descriptor.enumerable,
      get: descriptor.get,
      set(value) {
        const protectedCreditNode =
          this?.id === "cs_credit_ultrapack" ||
          this?.id === "cs_credit_plugintheme";

        if (protectedCreditNode) {
          const next = String(value ?? "");
          const current = descriptor.get.call(this);
          if (current === next) return;
        }

        descriptor.set.call(this, value);
      }
    });
  } catch (_error) {
    // Se o navegador não permitir redefinir o descriptor, não interrompe o boot.
  }
})();

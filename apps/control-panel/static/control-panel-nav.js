(() => {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".today-nav .nav-chip[href], .stage-flow .stage-step-link[href], .stage-flow .stage-jump[href]").forEach((link) => {
      if (link.target === "_blank") return;
      link.addEventListener("click", (event) => {
        if (
          event.defaultPrevented ||
          event.button !== 0 ||
          event.metaKey ||
          event.ctrlKey ||
          event.shiftKey ||
          event.altKey
        ) {
          return;
        }
        const href = link.getAttribute("href");
        if (!href || href.startsWith("#")) return;
        event.preventDefault();
        window.location.assign(href);
      });
    });
  });
})();

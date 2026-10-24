"""ASCII Magic loader for the "Grand Canyon Rim" background piece.

The piece is decoration only: the workspace panel on top of it stays opaque,
so every heading, table and number is read on solid paper and the art is only
ever seen around the edges and behind the header.

The module script is fetched once per browser session and the ``<ascii-art>``
element is created with ``document.createElement`` because Streamlit
sanitises rendered HTML and DOMPurify drops unknown custom elements.
"""

from __future__ import annotations

ASCII_MAGIC_SRC = "https://www.ascii-magic.com/ascii/ascii.js"

# Grand Canyon Rim is 192 x 108 cells. At size=10 the blocks look stays
# legible while the frame stays small enough to scale cleanly to a viewport.
ASCII_ART_SIZE = 10

ASCII_MAGIC_HTML = """
<script>
(function () {
  const BACKDROP_ID = "fs-ascii-backdrop";
  const ART_ID = "fs-ascii-art";
  const SCRIPT_ID = "fs-ascii-magic-script";
  const SRC = "https://www.ascii-magic.com/ascii/ascii.js";
  const CELL_WIDTH = 0.602;
  const COLS = 192;
  const ROWS = 108;
  const LINE_HEIGHT = 1.2;
  const SIZE = 10;

  if (!document.getElementById(SCRIPT_ID)) {
    const loader = document.createElement("script");
    loader.id = SCRIPT_ID;
    loader.type = "module";
    loader.src = SRC;
    document.head.appendChild(loader);
  }

  let backdrop = document.getElementById(BACKDROP_ID);
  if (!backdrop) {
    backdrop = document.createElement("div");
    backdrop.id = BACKDROP_ID;
    backdrop.setAttribute("aria-hidden", "true");
    document.body.appendChild(backdrop);
  }

  let art = document.getElementById(ART_ID);
  if (!art) {
    art = document.createElement("ascii-art");
    art.id = ART_ID;
    art.setAttribute("piece", "grand-canyon-rim");
    art.setAttribute("look", "blocks");
    art.setAttribute("size", String(SIZE));
    backdrop.appendChild(art);
  }

  function fit() {
    const baseWidth = COLS * CELL_WIDTH * SIZE;
    const baseHeight = ROWS * SIZE * LINE_HEIGHT;
    const scale = Math.max(window.innerWidth / baseWidth, window.innerHeight / baseHeight);
    backdrop.style.setProperty("--fs-ascii-scale", (scale + 0.02).toFixed(3));
  }

  if (!window.__fsAsciiFit) {
    window.__fsAsciiFit = fit;
    window.addEventListener(
      "resize",
      function () {
        window.clearTimeout(window.__fsAsciiResize);
        window.__fsAsciiResize = window.setTimeout(fit, 250);
      },
      { passive: true }
    );
  }
  fit();

  const container = document.currentScript && document.currentScript.parentElement;
  if (container) container.style.display = "none";
})();
</script>
"""

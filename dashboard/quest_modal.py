"""Popup that opens a day column's full task list from the weekly board.

The board renders every card in the DOM and hides the ones past the visible
limit, so this script only has to clone them into a modal. The click handling
is delegated from ``document``, so it survives Streamlit reruns that rebuild
the board markup.
"""

from __future__ import annotations

QUEST_MODAL_HTML = """
<script>
(function () {
  if (window.__fsQuestModalBound) return;
  window.__fsQuestModalBound = true;

  var MODAL_ID = "fs-quest-modal";

  function closeModal() {
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    var returnFocus = modal.__returnFocus;
    modal.remove();
    document.body.classList.remove("fs-modal-open");
    if (returnFocus && document.contains(returnFocus)) returnFocus.focus();
  }

  function openModal(button) {
    closeModal();
    var day = button.closest(".quest-day");
    if (!day) return;
    var cards = day.querySelectorAll(".quest-card");
    if (!cards.length) return;

    var overlay = document.createElement("div");
    overlay.id = MODAL_ID;
    overlay.className = "fs-quest-modal";
    overlay.__returnFocus = button;

    var panel = document.createElement("div");
    panel.className = "fs-quest-panel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
    panel.setAttribute("aria-labelledby", "fs-quest-title");

    var head = document.createElement("div");
    head.className = "fs-quest-head";

    var copy = document.createElement("div");
    var kicker = document.createElement("span");
    kicker.className = "fs-quest-kicker";
    kicker.textContent = "All tasks";
    var title = document.createElement("h3");
    title.className = "fs-quest-title";
    title.id = "fs-quest-title";
    title.textContent = (button.dataset.day || "Day") + " \\u00b7 " + cards.length + " tasks";
    var sub = document.createElement("div");
    sub.className = "fs-quest-sub";
    sub.textContent = button.dataset.date || "";
    copy.appendChild(kicker);
    copy.appendChild(title);
    copy.appendChild(sub);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "fs-quest-close";
    close.setAttribute("aria-label", "Close the task list");
    close.textContent = "\\u00d7";

    head.appendChild(copy);
    head.appendChild(close);

    var body = document.createElement("div");
    body.className = "fs-quest-body";
    cards.forEach(function (card) {
      body.appendChild(card.cloneNode(true));
    });

    panel.appendChild(head);
    panel.appendChild(body);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    document.body.classList.add("fs-modal-open");
    close.focus();
  }

  document.addEventListener("click", function (event) {
    var more = event.target.closest && event.target.closest(".quest-more");
    if (more) {
      event.preventDefault();
      openModal(more);
      return;
    }
    var modal = document.getElementById(MODAL_ID);
    if (!modal) return;
    if (
      event.target === modal ||
      (event.target.closest && event.target.closest(".fs-quest-close"))
    ) {
      closeModal();
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeModal();
  });
})();
</script>
"""

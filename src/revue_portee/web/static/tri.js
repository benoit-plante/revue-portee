// Keyboard screening (ENF-PER-02): i include, e exclude, d uncertain, 1-9 toggle the
// criteria, p skip. Registered once; the form is looked up at each key press, so it
// keeps working when hx-boost swaps the page.
(function () {
  if (window.revuePorteeTri) { return; }
  window.revuePorteeTri = true;
  document.addEventListener("keydown", function (event) {
    if (event.ctrlKey || event.metaKey || event.altKey) { return; }
    var target = event.target;
    if (target && (target.tagName === "TEXTAREA" || target.tagName === "SELECT" ||
        (target.tagName === "INPUT" && target.type !== "checkbox"))) { return; }
    var form = document.getElementById("tri-form");
    if (!form) { return; }
    var key = event.key.toLowerCase();
    var values = { i: "include", e: "exclude", d: "uncertain" };
    if (values[key]) {
      var button = form.querySelector('button[name="valeur"][value="' + values[key] + '"]');
      if (button) { event.preventDefault(); button.click(); }
      return;
    }
    if (key === "p") {
      var skip = document.getElementById("tri-passer");
      if (skip) { event.preventDefault(); skip.click(); }
      return;
    }
    if (/^[1-9]$/.test(key)) {
      var boxes = form.querySelectorAll('input[name="criteres"]');
      var box = boxes[Number(key) - 1];
      if (box) { event.preventDefault(); box.checked = !box.checked; box.focus(); }
    }
  });
})();

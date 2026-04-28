// Tiny enhancements; HTMX does the heavy lifting.
document.body.addEventListener("htmx:responseError", (e) => {
  const flash = document.getElementById("flash");
  if (flash) {
    flash.innerHTML = `<div class="flash flash-error">request failed: ${e.detail.xhr.status}</div>`;
    setTimeout(() => (flash.innerHTML = ""), 5000);
  }
});

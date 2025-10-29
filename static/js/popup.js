function handleAIResponse(response) {
  try {
    let data = JSON.parse(response);

    if (data.action === "SHOW_CONTACT_FORM") {
      document.getElementById("contactModal").style.display = "flex"; // SHOW modal
      return; // stop normal message display
    }

    // Otherwise show message normally in chat UI
    displayMessageToChat(data.message);

  } catch {
    // If response is not JSON, treat as normal chat text
    displayMessageToChat(response);
  }
}


document.getElementById("contactSubmit").onclick = async function () {
  const data = {
    fname: document.getElementById("fname").value,
    lname: document.getElementById("lname").value,
    email: document.getElementById("email").value,
    phone_number: document.getElementById("phone").value
  };

  await fetch("/save-contact", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  });

  // hide modal after submit
  document.getElementById("contactModal").style.display = "none";

  // instead of: alert("Thank you! Your details have been saved.");
  showToast("Thank you! Your details have been saved.", "success", 3500);
};

// Utility to open/close the contact modal with animation and no inline layout shifting

(function () {
  const modal = document.getElementById("contactModal");
  if (!modal) return;

  let _showTimer = null;

  window.showContactModal = function (opts = {}) {
    const delay = typeof opts.delayMs === "number" ? opts.delayMs : 0;
    const animation = opts.animation || null; // e.g. 'slide-left'
    // set animation class (applied even before open to set initial transform)
    modal.classList.remove("slide-left");
    if (animation === "slide-left") modal.classList.add("slide-left");

    const doShow = () => {
      modal.classList.add("open");
      // keep animation class applied on open too
      if (animation === "slide-left") modal.classList.add("slide-left");
      modal.dataset.metadata = opts.metadata ? JSON.stringify(opts.metadata) : "";
      const fname = modal.querySelector("#fname");
      if (fname) fname.focus();
    };

    // clear any previous pending show
    if (_showTimer) {
      clearTimeout(_showTimer);
      _showTimer = null;
    }

    if (delay > 0) {
      _showTimer = setTimeout(() => {
        doShow();
        _showTimer = null;
      }, delay);
    } else {
      doShow();
    }
  };

  window.hideContactModal = function () {
    // play reverse animation by removing open but keep slide-left class for initial state
    modal.classList.remove("open");
    // remove metadata
    delete modal.dataset.metadata;
    if (_showTimer) { clearTimeout(_showTimer); _showTimer = null; }
  };

  // wire up close/skip
  const closeBtn = modal.querySelector(".modal-close");
  if (closeBtn) closeBtn.addEventListener("click", () => hideContactModal());
  const skipBtn = modal.querySelector("#contactSkip");
  if (skipBtn) skipBtn.addEventListener("click", () => hideContactModal());

  // existing submit wiring (keeps behavior)
  const submitBtn = modal.querySelector("#contactSubmit") || modal.querySelector("#contactSend");
  if (submitBtn) {
    submitBtn.addEventListener("click", async () => {
      const payload = {
        fname: modal.querySelector("#fname")?.value || modal.querySelector("#contactFname")?.value || "",
        lname: modal.querySelector("#lname")?.value || modal.querySelector("#contactLname")?.value || "",
        email: modal.querySelector("#email")?.value || modal.querySelector("#contactEmail")?.value || "",
        phone_number: modal.querySelector("#phone")?.value || modal.querySelector("#contactPhone")?.value || ""
      };
      // optional: call your save endpoint here
      // await fetch("/save-contact", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify(payload) });
      hideContactModal();
    });
  }
})();

// Ensure toast is hidden on page load (prevent auto-show on reload)
document.addEventListener("DOMContentLoaded", () => {
  const toast = document.getElementById("toast");
  if (toast) {
    toast.classList.remove("show");
    // hide visually and remove any inline width set by previous runs
    toast.style.display = "none";
    toast.style.width = "";
  }
});

function showToast(message, type = "info", duration = 3000) {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    const body = document.createElement("div");
    body.className = "toast-body";
    toast.appendChild(body);
    document.body.appendChild(toast);
  }

  // make visible and size to content
  toast.style.display = "inline-block";
  let body = toast.querySelector(".toast-body");
  body.textContent = message;

  // reset classes then add new type
  toast.className = "";
  toast.classList.add(type);

  // force reflow so animation runs
  void toast.offsetWidth;
  toast.classList.add("show");

  // ensure width fits content
  toast.style.width = "auto";

  if (toast._hideTimer) clearTimeout(toast._hideTimer);
  toast._hideTimer = setTimeout(() => {
    toast.classList.remove("show");
    // after transition, hide element so it doesn't appear on reload
    setTimeout(() => {
      toast.className = "";
      toast.style.display = "none";
      toast.style.width = "";
    }, 260);
  }, duration);
}

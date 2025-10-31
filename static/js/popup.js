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
  let _showTimer = null;
  let _hideTimer = null;

  function getModal() {
    return document.getElementById("contactModal");
  }

  function ensureStructure() {
    const modal = getModal();
    if (!modal) return null;
    if (!modal.querySelector(".modal-content")) {
      // wrap existing children if needed
      const wrapper = document.createElement("div");
      wrapper.className = "modal-content";
      while (modal.firstChild) wrapper.appendChild(modal.firstChild);
      modal.appendChild(wrapper);
    }
    return modal;
  }

  function attachModalHandlers() {
    const modal = ensureStructure();
    if (!modal) return;

    const closeBtn = modal.querySelector(".modal-close");
    if (closeBtn) {
      closeBtn.onclick = () => hideContactModal();
    }

    const skipBtn = modal.querySelector("#contactSkip");
    if (skipBtn) {
      skipBtn.onclick = () => hideContactModal();
    }

    const submitBtn = modal.querySelector("#contactSubmit") || modal.querySelector("#contactSend");
    if (submitBtn) {
      // always reset to a known state
      submitBtn.disabled = false;
      submitBtn.onclick = async function (ev) {
        ev && ev.preventDefault();
        // guard double clicks
        if (submitBtn.disabled) return;
        submitBtn.disabled = true;

        // collect values
        const payload = {
          fname: modal.querySelector("#fname")?.value?.trim() || "",
          lname: modal.querySelector("#lname")?.value?.trim() || "",
          email: modal.querySelector("#email")?.value?.trim() || "",
          phone_number: modal.querySelector("#phone")?.value?.trim() || "",
          metadata: modal.dataset.metadata ? JSON.parse(modal.dataset.metadata) : {}
        };

        try {
          // send to backend but do not remove modal from DOM
          if (typeof fetch === "function") {
            const resp = await fetch("/save-contact", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(payload)
            });
            if (resp.ok) {
              try { showToast("Thank you — Our team will connect with you soon.", "success", 3000); } catch {}
            } else {
              try { showToast("Failed to save contact. Try again.", "error", 3500); } catch {}
            }
          }
        } catch (err) {
          console.warn("contact submit error", err);
          try { showToast("Network error while saving contact.", "error", 3500); } catch {}
        } finally {
          // reset and hide modal, but allow re-open
          submitBtn.disabled = false;
          // reset inputs so next open shows empty form
          const inputs = modal.querySelectorAll("input, textarea");
          inputs.forEach(i => i.value = "");
          hideContactModal();
        }
      };
    }
  }

  window.showContactModal = function (opts = {}) {
    const modal = ensureStructure();
    if (!modal) return;
    const delay = typeof opts.delayMs === "number" ? opts.delayMs : 0;
    const animation = opts.animation || null;

    // clear previous timers
    if (_showTimer) { clearTimeout(_showTimer); _showTimer = null; }
    if (_hideTimer) { clearTimeout(_hideTimer); _hideTimer = null; }

    // set animation class (kept; CSS should handle it)
    modal.classList.toggle("slide-left", animation === "slide-left");

    // store metadata
    modal.dataset.metadata = opts.metadata ? JSON.stringify(opts.metadata) : "";

    const doShow = () => {
      modal.style.display = "flex"; // ensure visible container
      // force layout then add open class so transitions run
      void modal.offsetWidth;
      modal.classList.add("open");
      // focus first field
      const first = modal.querySelector("#fname") || modal.querySelector("input");
      if (first) first.focus();
      // reattach handlers to current DOM
      attachModalHandlers();
    };

    if (delay > 0) {
      _showTimer = setTimeout(() => { doShow(); _showTimer = null; }, delay);
    } else {
      doShow();
    }
  };

  window.hideContactModal = function () {
    const modal = getModal();
    if (!modal) return;
    // cancel show timer
    if (_showTimer) { clearTimeout(_showTimer); _showTimer = null; }

    // remove open class to play transition out
    modal.classList.remove("open");

    // after transition hide visually and reset state
    if (_hideTimer) clearTimeout(_hideTimer);
    _hideTimer = setTimeout(() => {
      modal.style.display = "none";
      // cleanup classes but keep slide-left if desired (so next show keeps same animation)
      modal.classList.remove("slide-left");
      delete modal.dataset.metadata;
      // reset inputs so next open is fresh
      const inputs = modal.querySelectorAll("input, textarea");
      inputs.forEach(i => { i.value = ""; i.disabled = false; });
      const submitBtn = modal.querySelector("#contactSubmit") || modal.querySelector("#contactSend");
      if (submitBtn) submitBtn.disabled = false;
      _hideTimer = null;
    }, 260); // match CSS transition duration
  };

  // initialize on DOM ready
  document.addEventListener("DOMContentLoaded", () => {
    attachModalHandlers();
    // ensure modal hidden initially
    const modal = getModal();
    if (modal) {
      modal.classList.remove("open");
      modal.style.display = "none";
    }
  });

  // if scripts loaded after DOM, attach now as well
  attachModalHandlers();
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

(function () {
  function ensureToast() {
    let toast = document.getElementById("toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "toast";
      toast.setAttribute("aria-live", "polite");
      toast.setAttribute("role", "status");
      const body = document.createElement("div");
      body.className = "toast-body";
      toast.appendChild(body);
      document.body.appendChild(toast);
    } else {
      // ensure structure and remove any inline width/height that cause full-screen
      toast.style.width = "auto";
      toast.style.left = "";
      toast.style.top = "";
      toast.style.right = "20px";
      toast.style.bottom = "24px";
      if (!toast.querySelector(".toast-body")) {
        const body = document.createElement("div");
        body.className = "toast-body";
        toast.innerHTML = "";
        toast.appendChild(body);
      }
    }
    // ensure hidden state
    toast.classList.remove("show");
    toast.style.display = "none";
    return toast;
  }

  document.addEventListener("DOMContentLoaded", () => ensureToast());

  window.showToast = function (message, type = "info", duration = 3000) {
    const toast = ensureToast();
    const body = toast.querySelector(".toast-body");
    // use textContent to avoid accidental HTML injection
    body.textContent = message || "";
    // reset classes and add variant
    toast.className = "";            // clear classes like 'success' etc.
    toast.classList.add(type);
    // inline-block display to size to content
    toast.style.display = "inline-block";
    toast.style.width = "auto";
    // force reflow then animate in
    void toast.offsetWidth;
    toast.classList.add("show");

    if (toast._hideTimer) { clearTimeout(toast._hideTimer); toast._hideTimer = null; }
    toast._hideTimer = setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => {
        toast.style.display = "none";
        toast.className = "";
      }, 240);
    }, duration);
  };
})();

document.addEventListener("DOMContentLoaded", () => {
    // ---------- DOM Elements ----------
    const chatIcon = document.getElementById("chat-icon");
    const chatContainer = document.getElementById("chat-container");
    const chatBox = document.getElementById("chat-box");
    const userInput = document.getElementById("user-input");
    const sendBtn = document.getElementById("send-btn");
    const toast = document.getElementById("toast");
    const urlLoader = document.getElementById("url-loader");

    const sidebar = document.getElementById("left-sidebar");
    const toggleBtn = document.getElementById("sidebar-toggle");
    const closeBtn = document.getElementById("close-sidebar");
    const addBtn = document.getElementById("sidebar-add");
    const urlInput = document.getElementById("sidebar-url");
    const urlList = document.getElementById("sidebar-url-list");
    const firmSelect = document.getElementById("firm-select");

    let greeted = false;

    // ---------- Chat Toggle ----------
    chatIcon.onclick = () => {
        chatContainer.style.display = chatContainer.style.display === "flex" ? "none" : "flex";
        if (!greeted) {
            addMessage("Assistant is here, how may I help you? 😊", "bot-msg");
            greeted = true;
        }
    };

    // ---------- Sidebar Toggle ----------
    toggleBtn.onclick = () => {
        sidebar.style.left = "0";
        sidebar.classList.add("open");
        toggleBtn.style.display = "none";
    };

    closeBtn.onclick = () => {
        sidebar.style.left = "-260px";
        sidebar.classList.remove("open");
        toggleBtn.style.display = "block";
    };

    // ---------- Toast ----------
    function showToast(msg, isError = false) {
        toast.textContent = msg;
        toast.style.backgroundColor = isError ? "#e74c3c" : "#2ecc71";
        toast.style.display = "block";
        toast.style.animation = "none";
        toast.offsetHeight; // trigger reflow
        toast.style.animation = "fadeInOut 3s ease forwards";
        setTimeout(() => { toast.style.display = "none"; }, 3000);
    }

    // ---------- Chat Formatting ----------
    function parseMarkdownLinks(text) {
        return text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
            (match, label, url) => `<a href="${url}" target="_blank" style="color:#4a90e2;text-decoration:none;">${label}</a>`);
    }

    function formatResponse(msg) {
        msg = parseMarkdownLinks(msg);
        msg = msg.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
        const lines = msg.split("\n").map(l => l.trim()).filter(l => l);
        let output = "", listItems = [];
        lines.forEach(line => {
            if (/^\d+\.\s/.test(line)) listItems.push(line.replace(/^\d+\.\s/, ""));
            else {
                if (listItems.length) {
                    output += `<ol style="margin-left:20px;margin-top:10px;">${listItems.map(i => `<li style="margin-bottom:8px;">${i}</li>`).join("")}</ol>`;
                    listItems = [];
                }
                output += `<p style="margin-bottom:10px;">${line}</p>`;
            }
        });
        if (listItems.length)
            output += `<ol style="margin-left:20px;margin-top:10px;">${listItems.map(i => `<li style="margin-bottom:8px;">${i}</li>`).join("")}</ol>`;
        return output;
    }

    function addMessage(msg, className) {
        const div = document.createElement("div");
        div.className = "message " + className;
        div.innerHTML = formatResponse(msg);
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
        return div;
    }

    function createTypingIndicator() {
        const typingDiv = document.createElement("div");
        typingDiv.className = "message bot-msg typing-indicator";
        typingDiv.style.fontStyle = "italic";
        typingDiv.style.fontSize = "0.85rem";
        typingDiv.style.display = "flex";
        typingDiv.style.alignItems = "center";
        typingDiv.innerHTML = `<span>Assistant is typing</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
        return typingDiv;
    }

    function showTypingIndicatorAfter(messageDiv) {
        const typingDiv = createTypingIndicator();
        messageDiv.insertAdjacentElement('afterend', typingDiv);
        return typingDiv;
    }

    function removeTypingIndicator(typingDiv) {
        if (typingDiv && typingDiv.parentNode) typingDiv.remove();
    }

    async function typeMessage(element, msg, delay = 25) {
        element.innerHTML = "";
        msg = formatResponse(msg);
        let buffer = "", inTag = false;
        for (let i = 0; i < msg.length; i++) {
            const char = msg[i];
            buffer += char;
            if (char === "<") inTag = true;
            if (char === ">") inTag = false;
            if (!inTag) chatBox.scrollTop = chatBox.scrollHeight;
            element.innerHTML = buffer;
            await new Promise(r => setTimeout(r, delay));
        }
        element.innerHTML = buffer;
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function getSelectedFirm() {
        return firmSelect.value || null;
    }

    // ---------- Send Message ----------
    async function sendMessage() {
        const query = userInput.value.trim();
        if (!query) return;

        const selectedFirm = getSelectedFirm();
        if (!selectedFirm) {
            showToast("Please select a firm.", true);
            return;
        }

        const userMsgDiv = addMessage(query, "user-msg");
        userInput.value = "";
        const typingDiv = showTypingIndicatorAfter(userMsgDiv);

        try {
            const resp = await fetch("/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query, session_id: crypto.randomUUID(), firm_id: selectedFirm })
            });

            const data = await resp.json();
            removeTypingIndicator(typingDiv);

            if (!resp.ok) {
                const errMsg = data.detail || "⚠️ Something went wrong.";
                addMessage(errMsg, "bot-msg");
                return;
            }

            if (data && data.answer) {
                const botMsgDiv = addMessage("", "bot-msg");
                await typeMessage(botMsgDiv, data.answer, 3);
            } else {
                addMessage("⚠️ No valid response from assistant.", "bot-msg");
            }
        } catch (err) {
            removeTypingIndicator(typingDiv);
            console.error(err);
            addMessage("⚠️ Network error or backend issue occurred.", "bot-msg");
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    userInput.addEventListener("keypress", e => { if (e.key === "Enter") sendMessage(); });

    // ---------- Load Firms ----------
    async function loadFirms(selectLast = false, newFirmId = null) {
        try {
            const resp = await fetch("/firms");
            if (!resp.ok) throw new Error("Failed to fetch firms");
            const data = await resp.json();

            if (data.status === "success") {
                firmSelect.innerHTML = '<option value="">Select a firm</option>';
                data.firms.forEach(firm => {
                    const option = document.createElement("option");
                    option.value = firm.id;
                    option.textContent = firm.name;
                    firmSelect.appendChild(option);
                });

                // ---------- Select the last selected firm ----------
                const lastSelected = localStorage.getItem("selectedFirm");
                if (lastSelected && data.firms.some(f => f.id === lastSelected)) {
                    firmSelect.value = lastSelected;
                } else if (selectLast) {
                    firmSelect.value = newFirmId || (data.firms.length > 0 ? data.firms[data.firms.length - 1].id : "");
                }
            }
        } catch (err) {
            console.error("Error loading firms:", err);
        }
    }

    loadFirms();

    // ---------- Save selected firm on change ----------
    firmSelect.addEventListener("change", () => {
        if (firmSelect.value) localStorage.setItem("selectedFirm", firmSelect.value);
    });

    // ---------- Sidebar URL Injection ----------
    addBtn.addEventListener("click", async () => {
        const url = urlInput.value.trim();
        if (!url) {
            showToast("Please enter a valid URL.", true);
            return;
        }

        urlLoader.style.display = "flex";
        urlLoader.textContent = "Injecting URL... ⏳";

        try {
            const response = await fetch("/inject-url", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (data.status === "exists") {
                showToast(`⚠️ ${data.message}`, true);
            } else if (data.status === "success") {
                showToast("✅ URL added successfully!");

                // Refresh firm list and select the new firm automatically
                await loadFirms(true, data.data.firm_id);

                // Add URL to sidebar
                const entry = document.createElement("div");
                entry.textContent = data.data.url;
                urlList.appendChild(entry);

                urlInput.value = "";
            } else {
                showToast("Unexpected response from server", true);
            }
        } catch (err) {
            console.error(err);
            showToast("Failed to add URL.", true);
        } finally {
            urlLoader.style.display = "none";
        }
    });
});

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
    // convert markdown/link/bold/list -> HTML, safe minimal handling
    function parseMarkdownLinks(text) {
        if (typeof text !== "string") {
            if (text && typeof text.message === "string") text = text.message;
            else text = String(text || "");
        }

        // Preserve existing anchor tags: if HTML present, return as-is (we assume trusted source)
        if (/<\/?[a-z][\s\S]*>/i.test(text)) {
            return text;
        }

        // Bold **text**
        text = text.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

        // Markdown links [label](https://...)
        text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

        // Numbered lists: lines starting with "1. " or "2. " -> convert contiguous numbered lines to <ol>
        text = text.replace(/((?:^\d+\.\s.*(\r?\n|$))+)/gm, (match) => {
            const items = match.trim().split(/\r?\n/).map(l => l.replace(/^\d+\.\s*/, "").trim()).filter(Boolean);
            return `<ol>${items.map(i => `<li>${i}</li>`).join("")}</ol>\n`;
        });

        // Dash lists: lines starting with "- "
        text = text.replace(/((?:^- .*(\r?\n|$))+)/gim, (match) => {
            const items = match.trim().split(/\r?\n/).map(l => l.replace(/^- /, "").trim()).filter(Boolean);
            return `<ul>${items.map(i => `<li>${i}</li>`).join("")}</ul>\n`;
        });

        // Convert remaining newlines to <br> for simple paragraphs
        text = text.replace(/\r?\n{2,}/g, "</p><p>"); // double newline = new paragraph
        text = text.replace(/\r?\n/g, "<br>");

        // Wrap paragraphs if we used paragraph splitting
        if (text.includes("</p><p>") || !text.startsWith("<") ) {
            if (!text.startsWith("<p") && !text.startsWith("<ol") && !text.startsWith("<ul")) {
                text = `<p>${text}</p>`;
            }
        }

        return text;
    }

    function formatResponse(resp) {
        // Normalize object responses
        if (typeof resp === "object" && resp !== null) {
            if (typeof resp.message === "string") return parseMarkdownLinks(resp.message);
            if (typeof resp.answer === "string") return parseMarkdownLinks(resp.answer);
            // fallback to stringified object
            try { return parseMarkdownLinks(JSON.stringify(resp)); } catch { return parseMarkdownLinks(String(resp)); }
        }
        return parseMarkdownLinks(String(resp || ""));
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

    async function typeMessage(containerEl, resp, speed = 2) {
        const html = formatResponse(resp);

        // If HTML contains tags (links/lists etc.), don't type char-by-char (avoids broken tags)
        if (/<\/?[a-z][\s\S]*>/i.test(html)) {
            containerEl.innerHTML = html;
            return;
        }

        // Natural typing simulation:
        // - speed: multiplier (1 = normal, <1 faster, >1 slower)
        // - baseDelay: baseline ms per character
        const baseDelay = 12; // baseline ms per character
        const jitterFactor = 0.45; // randomness factor

        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

        containerEl.innerHTML = "";
        for (let i = 0; i < html.length; i++) {
            const ch = html.charAt(i);
            containerEl.innerHTML += ch;

            // Determine delay
            let delay = baseDelay * (speed || 1);

            // Shorter pause for spaces (simulate continuous typing)
            if (ch === " ") {
                delay *= 0.3;
            }

            // Slightly longer for commas
            if (ch === ",") {
                delay += baseDelay * 4;
            }

            // Longer pause for sentence endings
            if (ch === "." || ch === "!" || ch === "?") {
                // look ahead: if next char is also punctuation or end, make a longer pause
                delay += baseDelay * 20;
            }

            // Newline -> paragraph pause
            if (ch === "\n") {
                delay += baseDelay * 12;
            }

            // Add some jitter so it feels natural
            const jitter = (Math.random() - 0.5) * jitterFactor * delay;
            delay = Math.max(2, Math.round(delay + jitter));

            await sleep(delay);
        }
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
                // Attempt to parse structured JSON response (string or object)
                let consumed = false;
                try {
                    let parsed = typeof data.answer === "string" ? JSON.parse(data.answer) : data.answer;
                    if (parsed && parsed.action === "SHOW_CONTACT_FORM") {
                        const botMsgDiv = addMessage("", "bot-msg");
                        const assistantText = parsed.message || "Before we finish, please share your contact details.";
                        await typeMessage(botMsgDiv, assistantText, 3);

                        // Open contact modal with 2s delay and slide-left animation
                        try {
                            if (typeof window.showContactModal === "function") {
                                window.showContactModal({
                                    endpoint: "/save-contact",
                                    metadata: { conversationId: parsed.conversation_id || null },
                                    delayMs: 2000,
                                    animation: "slide-left"
                                }); 
                            } else {
                                // fallback: show modal after delay
                                setTimeout(() => {
                                    const modal = document.getElementById("contactModal");
                                    if (modal) {
                                        modal.classList.add("slide-left");
                                        modal.classList.add("open");
                                    }
                                }, 2000);
                            }
                        } catch (e) {
                            console.warn("Failed to open contact modal", e);
                        }

                        consumed = true;
                    }
                } catch (e) {
                    // not JSON or parsing failed -> treat as regular text
                    consumed = false;
                }

                if (!consumed) {
                    const botMsgDiv = addMessage("", "bot-msg");
                    await typeMessage(botMsgDiv, data.answer, 3);
                }
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

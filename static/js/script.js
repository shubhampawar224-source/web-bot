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
        const isVisible = chatContainer.style.display === "flex";
        chatContainer.style.display = isVisible ? "none" : "flex";
        
        if (!isVisible) {
            // Force positioning with inline styles to override any CSS conflicts
            chatContainer.style.position = "absolute";
            chatContainer.style.top = "70px"; // Below navbar (60px) + margin
            chatContainer.style.right = "20px";
            chatContainer.style.bottom = "20px";
            chatContainer.style.left = "auto";
            chatContainer.style.width = "450px";
            chatContainer.style.height = "calc(100vh - 110px)"; // Full height minus navbar and margins
            chatContainer.style.maxWidth = "calc(100vw - 40px)";
            chatContainer.style.maxHeight = "calc(100vh - 110px)";
            chatContainer.style.zIndex = "2100";
            
            // Ensure chat container stays within bounds when opening
            setTimeout(() => adjustChatPosition(), 100);
            
            if (!greeted) {
                addMessage("Assistant is here, how may I help you? 😊", "bot-msg");
                greeted = true;
            }
        }
    };

    // Function to adjust chat position to stay within viewport
    function adjustChatPosition() {
        const container = chatContainer;
        if (!container) return;
        
        // Force absolute positioning
        container.style.position = "absolute";
        
        // Get viewport dimensions
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const navbarHeight = 60; // Navbar height
        const margin = 20; // Base margin
        
        // Get container dimensions
        const containerWidth = 450; // Fixed width
        const availableHeight = viewportHeight - navbarHeight - (margin * 2); // Height minus navbar and margins
        
        // Calculate safe positions
        const maxRight = Math.max(10, viewportWidth - containerWidth - 10);
        const topPosition = navbarHeight + 10; // Below navbar + margin
        
        // Set safe position below navbar
        container.style.top = topPosition + "px";
        container.style.right = Math.min(margin, maxRight) + "px";
        container.style.bottom = margin + "px";
        container.style.left = "auto";
        
        // Ensure dimensions don't exceed viewport
        container.style.width = Math.min(450, viewportWidth - 40) + "px";
        container.style.height = Math.min(availableHeight, availableHeight) + "px";
        
        console.log("Chat positioned below navbar at:", {
            top: container.style.top,
            right: container.style.right,
            bottom: container.style.bottom,
            width: container.style.width,
            height: container.style.height,
            viewport: { width: viewportWidth, height: viewportHeight },
            availableHeight: availableHeight
        });
    }

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
    function showToast(message, isError = false, duration = 3000) {
        if (!toast) return;
        
        toast.textContent = message;
        toast.className = `toast show ${isError ? 'error' : 'success'}`;
        
        setTimeout(() => {
            toast.className = 'toast';
        }, duration);
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
        typingDiv.style.gap = "4px";
        typingDiv.innerHTML = `<span>Assistant is typing</span><span class="dot"></span><span class="dot"></span><span class="dot"></span>`;
        return typingDiv;
    }

    function showTypingIndicatorAfter(messageDiv) {
        const typingDiv = createTypingIndicator();
        // Add a slight delay to make it feel more natural
        setTimeout(() => {
            if (typingDiv.parentNode === null) {
                messageDiv.insertAdjacentElement('afterend', typingDiv);
                chatBox.scrollTop = chatBox.scrollHeight;
            }
        }, 300);
        return typingDiv;
    }

    function removeTypingIndicator(typingDiv) {
        if (typingDiv && typingDiv.parentNode) {
            // Add fade out animation before removing
            typingDiv.style.animation = "fadeOutTyping 0.2s ease-out forwards";
            setTimeout(() => {
                if (typingDiv.parentNode) {
                    typingDiv.remove();
                }
            }, 200);
        }
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

    // Window resize handler to keep chat container in bounds
    window.addEventListener("resize", () => {
        if (chatContainer.style.display === "flex") {
            adjustChatPosition();
        }
    });

    // Ensure page content stays within bounds
    document.addEventListener("DOMContentLoaded", () => {
        document.body.style.overflow = "hidden";
        document.documentElement.style.overflow = "hidden";
    });

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

    // ---------- Sidebar URL Injection (Direct) ----------
    addBtn.addEventListener("click", async () => {
        const url = urlInput.value.trim();
        
        if (!url) {
            showToast("Please enter a valid URL.", true);
            return;
        }

        urlLoader.style.display = "flex";
        urlLoader.textContent = "Processing URL... �";

        try {
            const response = await fetch("/inject-url", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ url })
            });

            const data = await response.json();

            if (data.status === "success") {
                showToast("✅ URL successfully processed and added to knowledge base!", false, 4000);
                
                // Clear the form
                urlInput.value = "";
                
                // Show success message
                setTimeout(() => {
                    showToast("🎉 The website content is now available for the chatbot!", false, 3000);
                }, 1500);
                
            } else if (data.status === "error") {
                if (data.message.includes("already exists")) {
                    showToast("⚠️ This URL is already available in our assistant's knowledge base.", true);
                } else if (data.message.includes("Invalid URL")) {
                    showToast("❌ Please enter a valid URL that starts with http:// or https://", true);
                } else {
                    showToast(`❌ ${data.message}`, true);
                }
            } else {
                showToast("❌ Unexpected response from server", true);
            }
        } catch (err) {
            console.error("URL injection error:", err);
            showToast("❌ Failed to process URL. Please try again.", true);
        } finally {
            urlLoader.style.display = "none";
        }
    });
});

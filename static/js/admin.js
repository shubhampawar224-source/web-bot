// Admin Dashboard JavaScript
class AdminDashboard {
    constructor() {
        console.log('🏗️ AdminDashboard constructor called');

        // Set global reference immediately
        window.adminDashboard = this;

        this.authToken = localStorage.getItem('admin_token');
        this.adminInfo = JSON.parse(localStorage.getItem('admin_info') || '{}');
        this.currentSection = 'dashboard';
        this.eventsbound = false; // Flag to prevent multiple event bindings
        this.loggingOut = false; // Flag to prevent multiple logout toasts

        console.log('📋 Constructor state:', {
            hasToken: !!this.authToken,
            hasInfo: Object.keys(this.adminInfo).length > 0,
            currentSection: this.currentSection
        });

        this.init();
    }

    async init() {
        console.log('🚀 Initializing AdminDashboard...');

        // Check for OAuth callback
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('token') && urlParams.has('admin')) {
            console.log('🔐 Handling OAuth callback...');
            // Handle OAuth callback
            this.handleOAuthCallback(urlParams);
            return;
        }

        // Check authentication first
        if (this.authToken) {
            console.log('🔑 Token found, validating session...');
            // Validate session with backend
            const isValid = await this.validateSession();
            if (isValid) {
                console.log('✅ Session valid, showing dashboard...');
                this.showDashboard();
                try {
                    this.loadDashboardData();
                } catch (error) {
                    console.error('❌ Error loading dashboard data:', error);
                }
                // Fetch and set current assistant voice in dropdown
                this.setCurrentVoiceDropdown();
            } else {
                console.log('❌ Session invalid, clearing and showing login...');
                // Clear invalid session and redirect to login page
                this.clearSession();
                this.redirectToLogin('Session expired. Please login again.');
            }
        } else {
            console.log('🔓 No token found, showing login...');
            // If we're on admin panel without token, redirect to login
            this.redirectToLogin();
        }
    }

    async setCurrentVoiceDropdown() {
        // Fetch the current assistant voice from backend
        try {
            const response = await fetch('/admin/get-voice', {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });
            if (!response.ok) return;
            const data = await response.json();
            const currentVoice = data.voice;
            const voiceSelect = document.getElementById('voice-select');
            if (voiceSelect && currentVoice) {
                voiceSelect.value = currentVoice;
            }
        } catch (e) {
            // ignore
        }

        console.log('🔧 Binding events...');
        this.bindEvents();

        // Check for redirect messages after showing login
        this.checkForRedirectMessages();

        console.log('✅ AdminDashboard initialization complete');
    }

    bindEvents() {
        // Prevent multiple event listener bindings
        if (this.eventsbound) {
            return;
        }
        this.eventsbound = true;

        // Login form
        const loginForm = document.getElementById('login-form');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        // Google sign-in button
        const googleSignInBtn = document.getElementById('google-signin-btn');
        if (googleSignInBtn) {
            googleSignInBtn.addEventListener('click', () => this.handleGoogleSignIn());
        }

        // Logout button
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => this.handleLogout(e));
        }

        // Navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', (e) => {
                this.handleNavigation(e);

                // Close mobile sidebar when navigation item is clicked
                if (window.innerWidth <= 768) {
                    const sidebar = document.getElementById('admin-sidebar');
                    sidebar.classList.remove('mobile-open');
                }
            });
        });

        // Sidebar toggle
        const sidebarToggle = document.getElementById('sidebar-toggle');
        if (sidebarToggle) {
            console.log('✅ Sidebar toggle button found');
            sidebarToggle.addEventListener('click', () => {
                console.log('🖱️ Sidebar toggle clicked');
                this.toggleSidebar();
            });
        } else {
            console.error('❌ Sidebar toggle button not found');
        }

        // Refresh buttons
        const refreshUrls = document.getElementById('refresh-urls');
        if (refreshUrls) {
            refreshUrls.addEventListener('click', () => this.loadUrlRequests());
        }

        // Bulk process URLs
        const bulkProcessBtn = document.getElementById('bulk-process-urls');
        if (bulkProcessBtn) {
            bulkProcessBtn.addEventListener('click', () => this.bulkProcessUrls());
        }

        // Bulk delete URLs
        const bulkDeleteBtn = document.getElementById('bulk-delete-urls');
        if (bulkDeleteBtn) {
            bulkDeleteBtn.addEventListener('click', () => this.confirmBulkDeleteUrls());
        }

        // URL filters
        const urlStatusFilter = document.getElementById('url-status-filter');
        if (urlStatusFilter) {
            urlStatusFilter.addEventListener('change', () => this.loadUrlRequests());
        }

        const urlSearch = document.getElementById('url-search');
        if (urlSearch) {
            urlSearch.addEventListener('input', () => this.filterUrls());
        }

        // Select all URLs checkbox
        const selectAllUrls = document.getElementById('select-all-urls');
        if (selectAllUrls) {
            selectAllUrls.addEventListener('change', (e) => {
                this.toggleSelectAllUrls(e.target.checked);
                this.updateBulkDeleteButton();
            });
        }

        // Add event listener for individual URL checkboxes (will be bound when table is rendered)
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('url-checkbox')) {
                this.updateBulkDeleteButton();
            }
        });

        // Admin URL injection form
        const showUrlInjection = document.getElementById('show-url-injection');
        if (showUrlInjection) {
            showUrlInjection.addEventListener('click', () => this.showUrlInjectionForm());
        }

        const hideUrlInjection = document.getElementById('hide-url-injection');
        if (hideUrlInjection) {
            hideUrlInjection.addEventListener('click', () => this.hideUrlInjectionForm());
        }

        const urlInjectionForm = document.getElementById('url-injection-form');
        if (urlInjectionForm) {
            urlInjectionForm.addEventListener('submit', (e) => this.handleUrlInjection(e));
        }

        // Knowledge Base upload form
        const showKnowledgeUpload = document.getElementById('show-knowledge-upload');
        if (showKnowledgeUpload) {
            showKnowledgeUpload.addEventListener('click', () => this.showKnowledgeUploadForm());
        }

        const hideKnowledgeUpload = document.getElementById('hide-knowledge-upload');
        if (hideKnowledgeUpload) {
            hideKnowledgeUpload.addEventListener('click', () => this.hideKnowledgeUploadForm());
        }

        const knowledgeForm = document.getElementById('knowledge-form');
        if (knowledgeForm) {
            knowledgeForm.addEventListener('submit', (e) => this.handleKnowledgeUpload(e));
        }

        // User management tabs
        document.querySelectorAll('.tab-btn').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchTab(e.target.dataset.tab));
        });

        // Refresh users button
        const refreshUsers = document.getElementById('refresh-users');
        if (refreshUsers) {
            refreshUsers.addEventListener('click', () => this.loadUsers());
        }

        // Merge duplicate firms button
        const mergeDuplicateFirms = document.getElementById('merge-duplicate-firms');
        if (mergeDuplicateFirms) {
            mergeDuplicateFirms.addEventListener('click', () => this.handleMergeDuplicateFirms());
        }

        // Admin Bot functionality
        window.toggleApiKeyVisibility = () => this.toggleApiKeyVisibility();
        window.saveApiKey = () => this.saveApiKey();

        // Admin Bot event listeners
        const updateApiKeyBtn = document.getElementById('update-admin-api-key');
        if (updateApiKeyBtn) {
            updateApiKeyBtn.addEventListener('click', () => this.showApiKeyForm());
        }

        const cancelApiForm = document.getElementById('cancel-api-form');
        if (cancelApiForm) {
            cancelApiForm.addEventListener('click', () => this.hideApiKeyForm());
        }

        const adminApiKeyForm = document.getElementById('admin-api-key-form');
        if (adminApiKeyForm) {
            adminApiKeyForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.saveApiKey();
            });
        }

        const toggleAdminKey = document.getElementById('toggle-admin-key');
        if (toggleAdminKey) {
            toggleAdminKey.addEventListener('click', () => this.toggleApiKeyVisibility());
        }

        // Voice Assistant change button event (fix: use correct IDs and button click)
        const voiceSelect = document.getElementById('voice-select');
        const changeVoiceBtn = document.getElementById('change-voice-btn');
        if (voiceSelect && changeVoiceBtn) {
            changeVoiceBtn.addEventListener('click', () => this.handleVoiceSelection(voiceSelect.value));
        }
    }

    // Handle voice selection from button click
    async handleVoiceSelection(selectedVoice) {
        const statusDiv = document.getElementById('voice-change-status');

        if (!selectedVoice) {
            if (statusDiv) {
                statusDiv.textContent = 'Please select a voice.';
                statusDiv.style.color = 'red';
            }
            return;
        }

        // Show loading
        if (statusDiv) {
            statusDiv.textContent = 'Updating voice...';
            statusDiv.style.color = '#007bff';
        }

        try {
            const response = await fetch('/admin/set-voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: JSON.stringify({ voice: selectedVoice })
            });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                if (statusDiv) {
                    statusDiv.textContent = 'Voice updated successfully!';
                    statusDiv.style.color = 'green';
                }
                this.showToast('Voice updated successfully!', 'success');
            } else {
                if (statusDiv) {
                    statusDiv.textContent = data.message || 'Failed to update voice.';
                    statusDiv.style.color = 'red';
                }
                this.showToast(data.message || 'Failed to update voice.', 'error');
            }
        } catch (error) {
            if (statusDiv) {
                statusDiv.textContent = 'Error updating voice.';
                statusDiv.style.color = 'red';
            }
            this.showToast('Error updating voice.', 'error');
        }
    }

    async handleLogin(e) {
        e.preventDefault();

        console.log('🔐 Admin login attempt started...');

        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('login-error');

        console.log('📋 Login credentials:', { username, password: '***' });

        try {
            console.log('📤 Sending login request...');
            const response = await fetch('/admin/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username, password }),
            });

            console.log('📥 Login response status:', response.status);
            const data = await response.json();
            console.log('📄 Login response data:', data);

            if (data.status === 'success') {
                console.log('✅ Login successful, setting up session...');
                this.authToken = data.token;
                this.adminInfo = data.admin;

                localStorage.setItem('admin_token', this.authToken);
                localStorage.setItem('admin_info', JSON.stringify(this.adminInfo));

                console.log('🔄 Showing dashboard...');
                this.showDashboard();

                console.log('📊 Loading dashboard data...');
                try {
                    this.loadDashboardData();
                } catch (error) {
                    console.error('❌ Error loading dashboard data (non-critical):', error);
                }

                // Show personalized welcome message
                const adminName = this.adminInfo.full_name || this.adminInfo.username || 'Admin';
                this.showToast(`Welcome back, ${adminName}!`, 'success');
                console.log('✅ Admin login process completed successfully');
            } else {
                console.log('❌ Login failed:', data.message);
                errorDiv.textContent = data.message;
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('❌ Login error:', error);
            errorDiv.textContent = 'Login failed. Please try again.';
            errorDiv.style.display = 'block';
        }
    }

    async handleSignup(e) {
        e.preventDefault();

        const username = document.getElementById('signup-username').value;
        const email = document.getElementById('signup-email').value;
        const fullName = document.getElementById('signup-full-name').value;
        const password = document.getElementById('signup-password').value;
        const confirmPassword = document.getElementById('signup-confirm-password').value;
        const isSuperAdmin = document.getElementById('signup-super-admin').checked;
        const errorDiv = document.getElementById('signup-error');

        // Hide previous errors
        errorDiv.style.display = 'none';

        // Validate passwords match
        if (password !== confirmPassword) {
            errorDiv.textContent = 'Passwords do not match';
            errorDiv.style.display = 'block';
            return;
        }

        // Validate password strength
        if (password.length < 6) {
            errorDiv.textContent = 'Password must be at least 6 characters long';
            errorDiv.style.display = 'block';
            return;
        }

        try {
            const response = await fetch('/admin/signup', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username,
                    email,
                    full_name: fullName || null,
                    password,
                    is_super_admin: isSuperAdmin
                }),
            });

            const data = await response.json();

            if (data.status === 'success') {
                this.showToast('Admin account created successfully! Please login.', 'success');
                this.showLogin();
                // Clear the signup form
                document.getElementById('signup-form').reset();
            } else {
                errorDiv.textContent = data.message;
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Signup error:', error);
            errorDiv.textContent = 'Signup failed. Please try again.';
            errorDiv.style.display = 'block';
        }
    }

    async handleGoogleSignIn() {
        try {
            const response = await fetch('/admin/oauth/google');
            const data = await response.json();

            if (data.status === 'success') {
                // Redirect to Google OAuth
                window.location.href = data.authorization_url;
            } else {
                this.showToast('Google sign-in setup failed', 'error');
            }
        } catch (error) {
            console.error('Google sign-in error:', error);
            this.showToast('Google sign-in failed', 'error');
        }
    }

    handleOAuthCallback(urlParams) {
        try {
            const token = urlParams.get('token');
            const adminInfo = JSON.parse(decodeURIComponent(urlParams.get('admin')));

            if (token && adminInfo) {
                this.authToken = token;
                this.adminInfo = adminInfo;

                localStorage.setItem('admin_token', this.authToken);
                localStorage.setItem('admin_info', JSON.stringify(this.adminInfo));

                // Clean URL
                window.history.replaceState({}, document.title, window.location.pathname);

                this.showDashboard();
                this.loadDashboardData();
                this.bindEvents();

                this.showToast(`Welcome ${adminInfo.full_name}!`, 'success');
            } else {
                throw new Error('Invalid OAuth response');
            }
        } catch (error) {
            console.error('OAuth callback error:', error);
            this.showToast('Google sign-in failed', 'error');
            this.showLogin();
            this.bindEvents();
        }
    }

    async handleLogout(e) {
        // Prevent multiple logout operations
        if (this.loggingOut) {
            return;
        }
        this.loggingOut = true;

        // Only prevent default if this is a manual logout (has event)
        if (e) {
            e.preventDefault();
        }

        try {
            await fetch('/admin/logout', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                },
            });
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            this.clearSession();

            // Only show toast for manual logout (when event exists)
            if (e) {
                this.showToast('Logged out successfully', 'info');
            }

            // Redirect to login page after a short delay to show the toast
            setTimeout(() => {
                window.location.href = '/admin';
            }, e ? 1000 : 0); // Shorter delay for automatic logout
        }
    }

    async validateSession() {
        if (!this.authToken) {
            return false;
        }

        try {
            const response = await fetch('/admin/validate-session', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json',
                },
            });

            const data = await response.json();

            if (data.status === 'success') {
                // Update admin info if provided
                if (data.admin) {
                    this.adminInfo = data.admin;
                    localStorage.setItem('admin_info', JSON.stringify(this.adminInfo));
                }
                return true;
            } else {
                console.log('Session validation failed:', data.message);
                return false;
            }
        } catch (error) {
            console.error('Session validation error:', error);
            return false;
        }
    }

    clearSession() {
        this.authToken = null;
        this.adminInfo = {};
        localStorage.removeItem('admin_token');
        localStorage.removeItem('admin_info');
    }

    redirectToLogin(message = '') {
        // Store message in sessionStorage to show on login page
        if (message) {
            sessionStorage.setItem('admin_login_message', message);
        }

        // Only redirect if we're not already on the admin login page
        if (!window.location.pathname.includes('/admin')) {
            console.log('🔄 Redirecting to admin login page...');
            window.location.href = '/admin';
        } else {
            // If we're already on admin page, just show the login form
            this.showLogin();
        }
    }

    checkForRedirectMessages() {
        const redirectMessage = sessionStorage.getItem('admin_login_message');
        if (redirectMessage) {
            // Show the message in the login error div
            const errorDiv = document.getElementById('login-error');
            if (errorDiv) {
                errorDiv.textContent = redirectMessage;
                errorDiv.style.display = 'block';
                errorDiv.style.backgroundColor = '#fff3cd';
                errorDiv.style.color = '#856404';
                errorDiv.style.borderColor = '#ffeaa7';
            }

            // Clear the message
            sessionStorage.removeItem('admin_login_message');

            // Hide the message after 5 seconds
            setTimeout(() => {
                if (errorDiv) {
                    errorDiv.style.display = 'none';
                }
            }, 5000);
        }
    }

    handleNavigation(e) {
        e.preventDefault();

        const section = e.target.closest('.nav-link').dataset.section;
        this.showSection(section);
    }

    showSection(sectionName) {
        // Update navigation
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.remove('active');
        });
        const navLink = document.querySelector(`[data-section="${sectionName}"]`);
        if (navLink) navLink.classList.add('active');

        // Hide all sections and show only the selected one
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
            section.style.display = 'none';
        });
        const targetSection = document.getElementById(`${sectionName}-section`);
        if (targetSection) {
            targetSection.classList.add('active');
            targetSection.style.display = '';
        }

        this.currentSection = sectionName;

        // Load section-specific data
        this.loadSectionData(sectionName);
    }

    async loadSectionData(section) {
        switch (section) {
            case 'dashboard':
                await this.loadDashboardStats();
                await this.loadRecentActivity();
                break;
            case 'url-management':
                await this.loadUrlRequests();
                break;
            case 'contacts':
                await this.loadContacts();
                break;
            case 'firms':
                await this.loadFirms();
                break;
            case 'user-management':
                await this.loadUsers(); // Load regular users by default (active tab)
                await this.loadAdminUsers(); // Also prepare admin users data
                break;
            case 'admin-bot':
                await this.loadAdminBotSection();
                break;
        }
    }

    async loadDashboardData() {
        await this.loadDashboardStats();
        await this.loadRecentActivity();
    }

    async loadAdminBotSection() {
        try {
            const response = await fetch('/admin/bot-status', {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json',
                }
            });
            const data = await response.json();
            this.updateApiKeyStatus(data.hasApiKey || false);
        } catch (error) {
            console.error('Error loading admin bot status:', error);
            this.updateApiKeyStatus(false);
        }
    }

    updateApiKeyStatus(hasApiKey) {
        const statusIcon = document.getElementById('api-status-icon');
        const statusMessage = document.getElementById('api-status-message');
        const updateButton = document.getElementById('update-admin-api-key');
        const buttonText = document.getElementById('api-button-text');
        const formContainer = document.getElementById('api-key-form-container');

        if (hasApiKey) {
            statusIcon.className = 'fas fa-check-circle';
            statusIcon.style.color = '#059669';
            statusMessage.textContent = 'OpenAI API key is stored securely and ready for bot operations';
            updateButton.style.display = 'inline-flex';
            buttonText.textContent = 'Update API Key';
        } else {
            statusIcon.className = 'fas fa-times-circle';
            statusIcon.style.color = '#dc2626';
            statusMessage.textContent = 'OpenAI API key required for bot functionality - Please configure your key';
            updateButton.style.display = 'inline-flex';
            buttonText.textContent = 'Add API Key';
        }

        // Hide form by default
        if (formContainer) {
            formContainer.style.display = 'none';
        }
    }

    toggleApiKeyVisibility() {
        const input = document.getElementById('admin-api-key');
        const icon = document.querySelector('#toggle-admin-key i');

        if (input.type === 'password') {
            input.type = 'text';
            icon.className = 'fas fa-eye-slash';
        } else {
            input.type = 'password';
            icon.className = 'fas fa-eye';
        }
    }

    async saveApiKey() {
        const apiKey = document.getElementById('admin-api-key').value.trim();

        if (!apiKey) {
            this.showToast('Please enter an API key', 'error');
            return;
        }

        try {
            const response = await fetch('/admin/save-api-key', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ apiKey }),
            });

            const result = await response.json();

            if (response.ok) {
                this.showToast('API key saved successfully!', 'success');
                this.updateApiKeyStatus(true);
                this.hideApiKeyForm();
                document.getElementById('admin-api-key').value = '';
            } else {
                this.showToast(result.message || 'Failed to save API key', 'error');
            }
        } catch (error) {
            console.error('Error saving API key:', error);
            this.showToast('Error saving API key', 'error');
        }
    }

    showApiKeyForm() {
        const formContainer = document.getElementById('api-key-form-container');
        formContainer.style.display = 'block';
    }

    hideApiKeyForm() {
        const formContainer = document.getElementById('api-key-form-container');
        formContainer.style.display = 'none';
        document.getElementById('admin-api-key').value = '';
    }

    async loadDashboardStats() {
        try {
            const response = await this.makeAuthenticatedRequest('/admin/stats');
            const data = await response.json();

            if (data.status === 'success') {
                const stats = data.stats;

                document.getElementById('total-urls').textContent = stats.total_urls;
                document.getElementById('pending-urls').textContent = stats.pending_urls;
                document.getElementById('total-contacts').textContent = stats.total_contacts;
                document.getElementById('total-firms').textContent = stats.total_firms;
            }
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    async loadRecentActivity() {
        try {
            // Load recent URL requests
            const urlResponse = await this.makeAuthenticatedRequest('/admin/url-requests?limit=5');
            const urlData = await urlResponse.json();

            if (urlData.status === 'success') {
                this.renderRecentUrls(urlData.requests.slice(0, 5));
            }

            // Load recent contacts
            const contactResponse = await this.makeAuthenticatedRequest('/admin/contacts?limit=5');
            const contactData = await contactResponse.json();

            if (contactData.status === 'success') {
                this.renderRecentContacts(contactData.contacts.slice(0, 5));
            }
        } catch (error) {
            console.error('Failed to load recent activity:', error);
        }
    }

    renderRecentUrls(urls) {
        const container = document.getElementById('recent-urls');

        if (urls.length === 0) {
            container.innerHTML = '<p class="no-data">No recent URL requests</p>';
            return;
        }

        container.innerHTML = urls.map(url => `
            <div class="activity-item">
                <div class="activity-content">
                    <strong>${url.url}</strong>
                    <p>Requested by: ${url.requester_email}</p>
                    <small>${this.formatDate(url.created_at)}</small>
                </div>
                <span class="status-badge status-${this.getStatusClass(url)}">${this.getStatusText(url)}</span>
            </div>
        `).join('');
    }

    renderRecentContacts(contacts) {
        const container = document.getElementById('recent-contacts');

        if (contacts.length === 0) {
            container.innerHTML = '<p class="no-data">No recent contacts</p>';
            return;
        }

        container.innerHTML = contacts.map(contact => `
            <div class="activity-item">
                <div class="activity-content">
                    <strong>${contact.fname} ${contact.lname}</strong>
                    <p>${contact.email}</p>
                    <small>${this.formatDate(contact.created_at)}</small>
                </div>
            </div>
        `).join('');
    }

    async loadUrlRequests() {
        try {
            const statusFilter = document.getElementById('url-status-filter').value;
            // Use the new endpoint that shows both email requests and direct injections
            const response = await this.makeAuthenticatedRequest('/admin/all-urls');
            const data = await response.json();

            if (data.status === 'success') {
                // Filter the results based on the status filter
                let filteredRequests = data.requests;

                if (statusFilter !== 'all') {
                    filteredRequests = data.requests.filter(request => {
                        switch (statusFilter) {
                            case 'pending':
                                return !request.is_confirmed && !request.is_expired;
                            case 'confirmed':
                                return request.is_confirmed && !request.is_processed;
                            case 'processed':
                                return request.is_processed;
                            case 'expired':
                                return request.is_expired;
                            case 'direct':
                                return request.source === 'direct_injection';
                            default:
                                return true;
                        }
                    });
                }

                this.renderUrlRequestsTable(filteredRequests);
            }
        } catch (error) {
            console.error('Failed to load URL requests:', error);
            this.showToast('Failed to load URL requests', 'error');
        }
    }

    renderUrlRequestsTable(requests) {
        const tbody = document.getElementById('urls-tbody');

        console.log('🔍 Rendering URL requests table with data:', requests.slice(0, 2)); // Log first 2 items for debugging

        if (requests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">No URL requests found</td></tr>';
            return;
        }

        tbody.innerHTML = requests.map(request => `
            <tr>
                <td>
                    <input type="checkbox" class="url-checkbox" value="${request.id || request.request_id}">
                </td>
                <td>
                    <div class="url-cell">
                        <a href="${request.url}" target="_blank" title="${request.url}">
                            ${this.truncateUrl(request.url)}
                        </a>
                    </div>
                </td>
                <td>
                    <div class="firm-cell">
                        <i class="fas fa-building"></i>
                        ${request.firm_name || 'Unknown'}
                    </div>
                </td>
                <td>
                    <div class="source-cell">
                        ${request.source === 'direct_injection' ?
                '<i class="fas fa-user-shield" style="color: #28a745;"></i> Admin Direct' :
                `<i class="fas fa-envelope" style="color: #007bff;"></i> ${request.requester_email}`
            }
                    </div>
                </td>
                <td>
                    <span class="status-badge status-${this.getStatusClass(request)}">
                        ${request.status_text || this.getStatusText(request)}
                    </span>
                </td>
                <td>${this.formatDate(request.created_at)}</td>
                <td>
                    ${this.getActionButtons(request)}
                </td>
            </tr>
        `).join('');

        this.bindTableEvents();
    }

    bindTableEvents() {
        // Process URL buttons
        document.querySelectorAll('.process-url-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const requestId = e.target.closest('.process-url-btn').dataset.requestId;
                this.processUrl(requestId);
            });
        });

        // View URL buttons
        document.querySelectorAll('.view-url-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const url = e.target.closest('.view-url-btn').dataset.url;
                window.open(url, '_blank');
            });
        });

        // Delete URL buttons
        document.querySelectorAll('.delete-url-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const button = e.target.closest('.delete-url-btn');
                const urlId = button.getAttribute('data-url-id');
                const url = button.getAttribute('data-url');
                const requester = button.getAttribute('data-requester');

                console.log('🔍 Delete button clicked, extracted data:', { urlId, url, requester });
                this.confirmDeleteUrl(urlId, url, requester);
            });
        });

        // Update bulk delete button visibility
        this.updateBulkDeleteButton();

        // Launch bot popup buttons
        document.querySelectorAll('.launch-bot-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const button = e.target.closest('.launch-bot-btn');
                const dbId = button.getAttribute('data-db-id');
                const requestId = button.getAttribute('data-request-id');
                const site = button.getAttribute('data-url') || '';
                const userId = button.getAttribute('data-user-id') || '';

                const params = new URLSearchParams();
                // prefer numeric db_id if available
                if (dbId) params.set('urls', dbId);
                else if (requestId) params.set('urls', requestId);
                if (site) params.set('site', site);
                if (userId) params.set('user_id', userId);

                const widgetUrl = `/widget?${params.toString()}`;

                // Popup size
                const width = 480;
                const height = 720;
                const left = window.screenX + Math.max(0, (window.outerWidth - width) / 2);
                const top = window.screenY + Math.max(0, (window.outerHeight - height) / 2);

                window.open(widgetUrl, '_blank', `toolbar=no,location=no,status=no,menubar=no,scrollbars=yes,resizable=yes,width=${width},height=${height},left=${left},top=${top}`);
            });
        });

        // Test widget new-tab buttons
        document.querySelectorAll('.test-widget-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const button = e.target.closest('.test-widget-btn');
                const dbId = button.getAttribute('data-db-id');
                const requestId = button.getAttribute('data-request-id');
                const site = button.getAttribute('data-url') || '';
                const userId = button.getAttribute('data-user-id') || '';

                const params = new URLSearchParams();
                if (dbId) params.set('urls', dbId);
                else if (requestId) params.set('urls', requestId);
                if (site) params.set('site', site);
                if (userId) params.set('user_id', userId);

                const url = `/widget?${params.toString()}`;
                window.open(url, '_blank');
            });
        });
    }

    async processUrl(requestId) {
        try {
            const response = await this.makeAuthenticatedRequest(`/admin/process-url/${requestId}`, {
                method: 'POST'
            });
            const data = await response.json();

            if (data.status === 'success') {
                this.showToast('URL processed successfully!', 'success');
                this.loadUrlRequests(); // Refresh the table
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (error) {
            console.error('Failed to process URL:', error);
            this.showToast('Failed to process URL', 'error');
        }
    }

    async removeUrl(requestId, email) {
        if (!confirm('Are you sure you want to remove this URL from the knowledge base? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await this.makeAuthenticatedRequest(`/remove-url/${requestId}`, {
                method: 'DELETE',
                body: JSON.stringify({ email: email })
            });
            const data = await response.json();

            if (data.status === 'success') {
                this.showToast('URL removed successfully!', 'success');
                this.loadUrlRequests(); // Refresh the table
                this.loadDashboardStats(); // Refresh stats
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (error) {
            console.error('Failed to remove URL:', error);
            this.showToast('Failed to remove URL', 'error');
        }
    }

    async bulkProcessUrls() {
        try {
            const response = await this.makeAuthenticatedRequest('/admin/bulk-process-urls', {
                method: 'POST'
            });
            const data = await response.json();

            if (data.status === 'success') {
                this.showToast(data.message, 'success');
                this.loadUrlRequests(); // Refresh the table
                this.loadDashboardStats(); // Refresh stats
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (error) {
            console.error('Failed to bulk process URLs:', error);
            this.showToast('Failed to process URLs', 'error');
        }
    }

    updateBulkDeleteButton() {
        const bulkDeleteBtn = document.getElementById('bulk-delete-urls');
        const selectedCheckboxes = document.querySelectorAll('.url-checkbox:checked');

        if (bulkDeleteBtn) {
            if (selectedCheckboxes.length > 0) {
                bulkDeleteBtn.style.display = 'inline-block';
                bulkDeleteBtn.textContent = `Delete Selected (${selectedCheckboxes.length})`;
            } else {
                bulkDeleteBtn.style.display = 'none';
            }
        }
    }

    confirmDeleteUrl(urlId, url, requester) {
        console.log('🔍 Delete URL called with:', { urlId, url, requester });

        if (!urlId || urlId === 'undefined') {
            console.error('❌ Invalid URL ID:', urlId);
            this.showToast('Error: Invalid URL ID', 'error');
            return;
        }

        // Show custom confirmation modal
        this.showDeleteConfirmation(urlId, url, requester);
    }

    confirmBulkDeleteUrls() {
        const selectedCheckboxes = document.querySelectorAll('.url-checkbox:checked');
        const selectedCount = selectedCheckboxes.length;

        if (selectedCount === 0) {
            this.showToast('Please select URLs to delete', 'warning');
            return;
        }

        const urlIds = Array.from(selectedCheckboxes).map(cb => cb.value);

        // Show custom bulk confirmation modal
        this.showBulkDeleteConfirmation(urlIds, selectedCount);
    }

    showDeleteConfirmation(urlId, url, requester) {
        // Set the data for the modal
        document.getElementById('delete-url-display').textContent = url;
        document.getElementById('delete-requester-display').textContent = requester;

        // Set up the confirm button
        const confirmBtn = document.getElementById('confirm-delete-btn');
        confirmBtn.onclick = () => {
            this.hideDeleteConfirmation();
            this.deleteUrl(urlId);
        };

        // Show the modal
        const modal = document.getElementById('delete-confirmation-modal');
        modal.style.display = 'flex';

        // Add click outside to close
        modal.onclick = (e) => {
            if (e.target === modal) {
                this.hideDeleteConfirmation();
            }
        };

        // Add escape key listener
        this.addEscapeKeyListener(() => this.hideDeleteConfirmation());
    }

    hideDeleteConfirmation() {
        const modal = document.getElementById('delete-confirmation-modal');
        modal.style.display = 'none';
        this.removeEscapeKeyListener();
    }

    showBulkDeleteConfirmation(urlIds, count) {
        // Set the data for the modal
        document.getElementById('bulk-delete-count-display').textContent = `${count} URLs`;
        document.getElementById('bulk-delete-confirmation-message').textContent =
            `Are you sure you want to delete ${count} selected URL(s)?`;

        // Set up the confirm button
        const confirmBtn = document.getElementById('confirm-bulk-delete-btn');
        confirmBtn.onclick = () => {
            this.hideBulkDeleteConfirmation();
            this.bulkDeleteUrls(urlIds);
        };

        // Show the modal
        const modal = document.getElementById('bulk-delete-confirmation-modal');
        modal.style.display = 'flex';

        // Add click outside to close
        modal.onclick = (e) => {
            if (e.target === modal) {
                this.hideBulkDeleteConfirmation();
            }
        };

        // Add escape key listener
        this.addEscapeKeyListener(() => this.hideBulkDeleteConfirmation());
    }

    hideBulkDeleteConfirmation() {
        const modal = document.getElementById('bulk-delete-confirmation-modal');
        modal.style.display = 'none';
        this.removeEscapeKeyListener();
    }

    addEscapeKeyListener(callback) {
        this.escapeKeyHandler = (e) => {
            if (e.key === 'Escape') {
                callback();
            }
        };
        document.addEventListener('keydown', this.escapeKeyHandler);
    }

    removeEscapeKeyListener() {
        if (this.escapeKeyHandler) {
            document.removeEventListener('keydown', this.escapeKeyHandler);
            this.escapeKeyHandler = null;
        }
    }

    async deleteUrl(urlId) {
        try {
            console.log('🗑️ Deleting URL with ID:', urlId);

            if (!urlId || urlId === 'undefined') {
                throw new Error('Invalid URL ID provided');
            }

            const response = await this.makeAuthenticatedRequest(`/admin/delete-url/${urlId}`, {
                method: 'DELETE'
            });

            console.log('📥 Delete response status:', response.status);
            const data = await response.json();
            console.log('📄 Delete response data:', data);

            if (data.status === 'success') {
                this.showToast(`Successfully deleted URL: ${data.data.deleted_url}`, 'success');
                this.loadUrlRequests(); // Refresh the table
                this.loadDashboardStats(); // Refresh stats
            } else {
                this.showToast(`Failed to delete URL: ${data.message}`, 'error');
            }
        } catch (error) {
            console.error('❌ Failed to delete URL:', error);
            this.showToast('Failed to delete URL: ' + error.message, 'error');
        }
    }

    async bulkDeleteUrls(urlIds) {
        try {
            console.log('🗑️ Bulk deleting URLs:', urlIds);

            const response = await this.makeAuthenticatedRequest('/admin/bulk-delete-urls', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: JSON.stringify({ url_ids: urlIds })
            });

            const data = await response.json();

            if (data.status === 'success') {
                const message = `Successfully deleted ${data.data.deleted_count} URL(s)`;
                this.showToast(message, 'success');

                if (data.data.failed_count > 0) {
                    this.showToast(`${data.data.failed_count} URL(s) failed to delete`, 'warning');
                }

                this.loadUrlRequests(); // Refresh the table
                this.loadDashboardStats(); // Refresh stats
                this.updateBulkDeleteButton(); // Hide bulk delete button
            } else {
                this.showToast(`Failed to delete URLs: ${data.message}`, 'error');
            }
        } catch (error) {
            console.error('Failed to bulk delete URLs:', error);
            this.showToast('Failed to delete URLs', 'error');
        }
    }

    async loadContacts() {
        try {
            const response = await this.makeAuthenticatedRequest('/admin/contacts');
            const data = await response.json();

            if (data.status === 'success') {
                this.renderContactsTable(data.contacts);
            }
        } catch (error) {
            console.error('Failed to load contacts:', error);
            this.showToast('Failed to load contacts', 'error');
        }
    }

    renderContactsTable(contacts) {
        const tbody = document.getElementById('contacts-tbody');

        if (contacts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center">No contacts found</td></tr>';
            return;
        }

        tbody.innerHTML = contacts.map(contact => `
            <tr>
                <td>${contact.fname} ${contact.lname}</td>
                <td>${contact.email}</td>
                <td>${contact.phone_number || 'N/A'}</td>
                <td>${this.formatDate(contact.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-danger delete-contact-btn" 
                            data-id="${contact.id}"
                            data-name="${contact.fname} ${contact.lname}"
                            data-email="${contact.email}"
                            data-phone="${contact.phone_number || 'N/A'}">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');

        // Bind delete buttons
        document.querySelectorAll('.delete-contact-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const button = e.target.closest('button');
                const contactId = button.dataset.id;
                const contactName = button.dataset.name;
                const contactEmail = button.dataset.email;
                const contactPhone = button.dataset.phone;
                this.confirmDeleteContact(contactId, contactName, contactEmail, contactPhone);
            });
        });
    }

    confirmDeleteContact(contactId, contactName, contactEmail, contactPhone) {
        // Set the data for the modal
        document.getElementById('delete-contact-name-display').textContent = contactName;
        document.getElementById('delete-contact-email-display').textContent = contactEmail;
        document.getElementById('delete-contact-phone-display').textContent = contactPhone;

        // Set up the confirm button
        const confirmBtn = document.getElementById('confirm-contact-delete-btn');
        confirmBtn.onclick = () => {
            this.hideContactDeleteConfirmation();
            this.deleteContact(contactId);
        };

        // Show the modal
        const modal = document.getElementById('contact-delete-confirmation-modal');
        modal.style.display = 'flex';

        // Add click outside to close
        modal.onclick = (e) => {
            if (e.target === modal) {
                this.hideContactDeleteConfirmation();
            }
        };

        // Add escape key listener
        this.addEscapeKeyListener(() => this.hideContactDeleteConfirmation());
    }

    hideContactDeleteConfirmation() {
        const modal = document.getElementById('contact-delete-confirmation-modal');
        modal.style.display = 'none';
        this.removeEscapeKeyListener();
    }

    async deleteContact(contactId) {
        try {
            const response = await this.makeAuthenticatedRequest(`/admin/contact/${contactId}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.status === 'success') {
                this.showToast('Contact deleted successfully!', 'success');
                this.loadContacts(); // Refresh the table
                this.loadDashboardStats(); // Refresh stats if applicable
            } else {
                this.showToast(data.message, 'error');
            }
        } catch (error) {
            console.error('Failed to delete contact:', error);
            this.showToast('Failed to delete contact', 'error');
        }
    }

    async loadFirms() {
        try {
            const response = await this.makeAuthenticatedRequest('/admin/firms');
            const data = await response.json();

            if (data.status === 'success') {
                this.renderFirmsTable(data.firms);
            }
        } catch (error) {
            console.error('Failed to load firms:', error);
            this.showToast('Failed to load firms', 'error');
        }
    }

    renderFirmsTable(firms) {
        const tbody = document.getElementById('firms-tbody');

        if (firms.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center">No firms found</td></tr>';
            return;
        }

        tbody.innerHTML = firms.map(firm => `
            <tr>
                <td>${firm.name}</td>
                <td>${firm.website_count || 0}</td>
                <td>${this.formatDate(firm.created_at)}</td>
                <td>
                    <button class="btn btn-sm btn-secondary view-firm-btn" data-id="${firm.id}">
                        <i class="fas fa-eye"></i> View
                    </button>
                </td>
            </tr>
        `).join('');
    }

    async loadAdminUsers() {
        // Placeholder for admin users management
        const tbody = document.getElementById('admins-tbody');
        tbody.innerHTML = `
            <tr>
                <td>${this.adminInfo.username}</td>
                <td>${this.adminInfo.email}</td>
                <td>${this.adminInfo.full_name || 'N/A'}</td>
                <td>${this.adminInfo.is_super_admin ? 'Super Admin' : 'Admin'}</td>
                <td>Active</td>
                <td>Active</td>
                
            </tr>
        `;
    }

    // Utility methods
    async makeAuthenticatedRequest(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Authorization': `Bearer ${this.authToken}`,
                'Content-Type': 'application/json',
                ...options.headers
            }
        };

        const response = await fetch(url, { ...defaultOptions, ...options });

        if (response.status === 401) {
            this.handleLogout();
            throw new Error('Authentication failed');
        }

        return response;
    }

    showLogin() {
        document.getElementById('loading-overlay').style.display = 'none';
        document.getElementById('admin-login').style.display = 'flex';
        document.getElementById('admin-dashboard').style.display = 'none';

        // Check for redirect messages when showing login
        setTimeout(() => this.checkForRedirectMessages(), 100);
    }

    showDashboard() {
        console.log('🏠 showDashboard() called');

        const loadingOverlay = document.getElementById('loading-overlay');
        const adminLogin = document.getElementById('admin-login');
        const adminDashboard = document.getElementById('admin-dashboard');

        console.log('📋 Dashboard elements:', {
            loadingOverlay: !!loadingOverlay,
            adminLogin: !!adminLogin,
            adminDashboard: !!adminDashboard
        });

        if (loadingOverlay) loadingOverlay.style.display = 'none';
        if (adminLogin) adminLogin.style.display = 'none';
        if (adminDashboard) adminDashboard.style.display = 'block';

        // Update admin name
        const adminNameEl = document.getElementById('admin-name');
        if (adminNameEl && this.adminInfo) {
            const displayName = this.adminInfo.full_name || this.adminInfo.username || 'Administrator';
            adminNameEl.textContent = displayName;
            console.log('👤 Admin name updated to:', displayName);
        }

        console.log('✅ Dashboard should now be visible');
    }

    toggleSidebar() {
        console.log('🔄 toggleSidebar() called');

        const dashboard = document.querySelector('.admin-dashboard');
        const sidebar = document.getElementById('admin-sidebar');
        const isMobile = window.innerWidth <= 768;

        console.log('📋 Elements found:', {
            dashboard: !!dashboard,
            sidebar: !!sidebar,
            isMobile: isMobile,
            windowWidth: window.innerWidth
        });

        if (isMobile) {
            // Mobile: toggle slide-out sidebar
            if (sidebar) {
                sidebar.classList.toggle('mobile-open');
                console.log('📱 Mobile sidebar toggled, classes:', sidebar.classList.toString());
            }
        } else {
            // Desktop: toggle collapsed sidebar
            if (dashboard) {
                const isCollapsed = dashboard.classList.contains('sidebar-collapsed');
                console.log('📊 Current state - isCollapsed:', isCollapsed);

                if (isCollapsed) {
                    dashboard.classList.remove('sidebar-collapsed');
                    console.log('🔄 Desktop sidebar expanded, classes:', dashboard.classList.toString());
                } else {
                    dashboard.classList.add('sidebar-collapsed');
                    console.log('🔄 Desktop sidebar collapsed, classes:', dashboard.classList.toString());
                }
            }
        }
    }

    filterUrls() {
        const searchTerm = document.getElementById('url-search').value.toLowerCase();
        const rows = document.querySelectorAll('#urls-tbody tr');

        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(searchTerm) ? '' : 'none';
        });
    }

    toggleSelectAllUrls(checked) {
        document.querySelectorAll('.url-checkbox').forEach(checkbox => {
            checkbox.checked = checked;
        });
    }

    getStatusClass(request) {
        if (request.is_expired) return 'expired';
        if (request.is_processed) return 'processed';
        if (request.is_confirmed) return 'confirmed';
        return 'pending';
    }

    getStatusText(request) {
        if (request.is_expired) return 'Expired';
        if (request.is_processed) return 'Processed';
        if (request.is_confirmed) return 'Confirmed';
        return 'Pending';
    }

    getActionButtons(request) {
        let buttons = `
            <button class="btn btn-sm btn-secondary view-url-btn" data-url="${request.url}">
                <i class="fas fa-external-link-alt"></i>
            </button>
        `;

        // Launch Bot button (opens widget in a popup window)
        buttons += `
            <button class="btn btn-sm btn-success launch-bot-btn" data-url="${request.url}" data-request-id="${request.request_id || ''}" data-db-id="${request.db_id || ''}" data-user-id="${request.user_id || ''}" data-firm="${(request.firm_name || '').replace(/"/g, '')}">
                <i class="fas fa-rocket"></i>
            </button>
        `;

        // Quick open in new tab (test) - keeps existing behavior if needed
        buttons += `
            <button class="btn btn-sm btn-info test-widget-btn" data-url="${request.url}" data-request-id="${request.request_id || ''}" data-db-id="${request.db_id || ''}" data-user-id="${request.user_id || ''}" data-firm="${(request.firm_name || '').replace(/"/g, '')}">
                <i class="fas fa-robot"></i>
            </button>
        `;

        if (request.is_confirmed && !request.is_processed && !request.is_expired) {
            buttons += `
                <button class="btn btn-sm btn-success process-url-btn" data-request-id="${request.request_id}">
                    <i class="fas fa-cogs"></i> Process
                </button>
            `;
        }

        // Add delete button for all URLs (admin can delete any URL)
        buttons += `
            <button class="btn btn-sm btn-danger delete-url-btn" 
                    data-url-id="${request.id}" 
                    data-url="${request.url}" 
                    data-requester="${request.requester_email || 'Direct Injection'}"
                    title="Delete this URL permanently">
                <i class="fas fa-trash"></i>
            </button>
        `;

        return buttons;
    }

    truncateUrl(url, maxLength = 50) {
        return url.length > maxLength ? url.substring(0, maxLength) + '...' : url;
    }

    formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
    }

    showToast(message, type = 'info') {
        const toastContainer = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;

        toast.innerHTML = `
            <i class="fas fa-${this.getToastIcon(type)}"></i>
            <span>${message}</span>
        `;

        toastContainer.appendChild(toast);

        // Trigger animation
        setTimeout(() => toast.classList.add('show'), 100);

        // Remove toast after 5 seconds
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toastContainer.removeChild(toast), 300);
        }, 5000);
    }

    getToastIcon(type) {
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        return icons[type] || 'info-circle';
    }

    // Admin URL Injection Methods
    showUrlInjectionForm() {
        const formContainer = document.getElementById('admin-url-injection-form');
        if (formContainer) {
            formContainer.style.display = 'block';
            document.getElementById('injection-url').focus();
            // Hide any previous status
            this.hideInjectionStatus();
        }
    }

    hideUrlInjectionForm() {
        const formContainer = document.getElementById('admin-url-injection-form');
        if (formContainer) {
            formContainer.style.display = 'none';
            // Clear form
            document.getElementById('url-injection-form').reset();
            this.hideInjectionStatus();
        }
    }

    showInjectionStatus(message, type) {
        const statusDiv = document.getElementById('injection-status');
        if (statusDiv) {
            statusDiv.textContent = message;
            statusDiv.className = `injection-status ${type}`;
            statusDiv.style.display = 'block';
        }
    }

    hideInjectionStatus() {
        const statusDiv = document.getElementById('injection-status');
        if (statusDiv) {
            statusDiv.style.display = 'none';
        }
    }

    // Knowledge Base Upload Methods
    async showKnowledgeUploadForm() {
        const formContainer = document.getElementById('knowledge-upload-form');
        if (formContainer) {
            formContainer.style.display = 'block';
            this.hideKnowledgeStatus();

            // Load firm names
            await this.loadFirmNamesForKnowledge();
        }
    }

    async loadFirmNamesForKnowledge() {
        try {
            const response = await fetch('/admin/firms', {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });

            const result = await response.json();

            if (result.status === 'success' && result.firms) {
                const selectElement = document.getElementById('firm-name-kb');
                const customInput = document.getElementById('firm-name-kb-custom');

                if (selectElement) {
                    // Clear existing options except the first one
                    selectElement.innerHTML = '<option value="">-- Select Existing Firm or Enter New --</option>';

                    // Add "Enter Custom" option
                    const customOption = document.createElement('option');
                    customOption.value = '__custom__';
                    customOption.textContent = '✏️ Enter Custom Firm Name';
                    selectElement.appendChild(customOption);

                    // Add all firms
                    result.firms.forEach(firm => {
                        const option = document.createElement('option');
                        option.value = firm.name;
                        option.textContent = `${firm.name} (${firm.website_count} websites)`;
                        selectElement.appendChild(option);
                    });

                    // Handle custom input toggle
                    selectElement.addEventListener('change', (e) => {
                        if (e.target.value === '__custom__') {
                            customInput.style.display = 'block';
                            customInput.focus();
                        } else {
                            customInput.style.display = 'none';
                            customInput.value = '';
                        }
                    });
                }
            }
        } catch (error) {
            console.error('Failed to load firm names:', error);
        }
    }

    hideKnowledgeUploadForm() {
        const formContainer = document.getElementById('knowledge-upload-form');
        if (formContainer) {
            formContainer.style.display = 'none';
            document.getElementById('knowledge-form').reset();
            // Hide custom input
            const customInput = document.getElementById('firm-name-kb-custom');
            if (customInput) {
                customInput.style.display = 'none';
                customInput.value = '';
            }
            this.hideKnowledgeStatus();
        }
    }

    showKnowledgeStatus(message, type) {
        const statusDiv = document.getElementById('knowledge-status');
        if (statusDiv) {
            statusDiv.textContent = message;
            statusDiv.className = `injection-status ${type}`;
            statusDiv.style.display = 'block';
        }
    }

    hideKnowledgeStatus() {
        const statusDiv = document.getElementById('knowledge-status');
        if (statusDiv) {
            statusDiv.style.display = 'none';
        }
    }

    async handleKnowledgeUpload(e) {
        e.preventDefault();

        const firmSelect = document.getElementById('firm-name-kb');
        const firmCustomInput = document.getElementById('firm-name-kb-custom');
        let firmName = '';

        // Determine firm name from select or custom input
        if (firmSelect.value === '__custom__') {
            firmName = firmCustomInput.value.trim();
        } else {
            firmName = firmSelect.value.trim();
        }

        const knowledgeType = document.getElementById('knowledge-type').value;
        const knowledgeText = document.getElementById('knowledge-text').value.trim();
        const fileInput = document.getElementById('knowledge-file');
        const file = fileInput.files[0];

        // Validate that either file or text is provided
        if (!file && !knowledgeText) {
            this.showKnowledgeStatus('Please upload a file or enter text content', 'error');
            return;
        }

        if (knowledgeText && knowledgeText.length < 50) {
            this.showKnowledgeStatus('Text content must be at least 50 characters', 'error');
            return;
        }

        this.showKnowledgeStatus('Uploading knowledge to vector store...', 'info');

        try {
            const formData = new FormData();
            formData.append('firm_name', firmName);
            formData.append('knowledge_type', knowledgeType);
            formData.append('knowledge_text', knowledgeText);

            if (file) {
                formData.append('knowledge_file', file);
            }

            const response = await fetch('/admin/upload-knowledge', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                },
                body: formData
            });

            const result = await response.json();

            if (result.status === 'success') {
                this.showKnowledgeStatus(
                    `✅ ${result.message}. Added ${result.chunks_added} knowledge chunks.`,
                    'success'
                );
                this.showToast('Knowledge uploaded successfully!', 'success');

                // Reset form after 2 seconds
                setTimeout(() => {
                    document.getElementById('knowledge-form').reset();
                    // Hide custom input
                    const customInput = document.getElementById('firm-name-kb-custom');
                    if (customInput) {
                        customInput.style.display = 'none';
                        customInput.value = '';
                    }
                    this.hideKnowledgeStatus();
                }, 2000);
            } else {
                this.showKnowledgeStatus(`❌ ${result.message}`, 'error');
                this.showToast('Failed to upload knowledge', 'error');
            }
        } catch (error) {
            console.error('Knowledge upload error:', error);
            this.showKnowledgeStatus('❌ Upload failed. Please try again.', 'error');
            this.showToast('Failed to upload knowledge', 'error');
        }
    }

    async handleUrlInjection(e) {
        e.preventDefault();

        const url = document.getElementById('injection-url').value.trim();

        if (!url) {
            this.showToast('Please enter a valid URL', 'error');
            return;
        }

        // Validate URL format
        try {
            new URL(url);
        } catch {
            this.showToast('Please enter a valid URL starting with http:// or https://', 'error');
            return;
        }

        this.showInjectionStatus('Processing URL and scraping content...', 'processing');

        try {
            const response = await this.makeAuthenticatedRequest('/admin/inject-url', {
                method: 'POST',
                body: JSON.stringify({ url: url })
            });

            const data = await response.json();

            if (data.status === 'success') {
                const taskId = data.task_id;
                this.showInjectionStatus('✅ URL processing started in background...', 'processing');
                this.showToast('URL processing started! Monitoring progress...', 'info');

                // Monitor task progress
                this.monitorTaskProgress(taskId, url);

            } else {
                this.showInjectionStatus(`❌ ${data.message}`, 'error');
                this.showToast(data.message, 'error');
            }
        } catch (error) {
            console.error('URL injection error:', error);
            this.showInjectionStatus('❌ Failed to process URL. Please try again.', 'error');
            this.showToast('Failed to inject URL. Please try again.', 'error');
        }
    }

    // Monitor background task progress
    async monitorTaskProgress(taskId, url) {
        const maxChecks = 60; // Maximum 5 minutes (60 * 5 seconds)
        let checks = 0;

        const checkProgress = async () => {
            try {
                const response = await fetch(`/task-status/${taskId}`);
                const data = await response.json();

                if (data.status === 'success' && data.task) {
                    const task = data.task;
                    const progress = task.progress || 0;
                    const status = task.status;
                    const message = task.message || '';

                    // Update status display with progress
                    this.showInjectionStatus(`📊 ${message} (${progress}%)`, 'processing');

                    if (status === 'completed') {
                        const result = task.result || {};
                        this.showInjectionStatus(`✅ Successfully processed ${result.indexed_chunks || 0} content chunks!`, 'success');
                        this.showToast('URL successfully injected and processed!', 'success');

                        // Clear form and refresh data
                        setTimeout(() => {
                            this.hideUrlInjectionForm();
                            this.loadUrlRequests();
                            this.loadDashboardStats();
                        }, 2000);

                        return; // Stop monitoring
                    } else if (status === 'failed') {
                        const error = task.error || 'Unknown error';
                        this.showInjectionStatus(`❌ Processing failed: ${message}`, 'error');
                        this.showToast(`Processing failed: ${message}`, 'error');
                        return; // Stop monitoring
                    }

                    // Continue monitoring if still processing
                    checks++;
                    if (checks < maxChecks) {
                        setTimeout(checkProgress, 5000); // Check every 5 seconds
                    } else {
                        this.showInjectionStatus('⚠️ Processing is taking longer than expected...', 'warning');
                        this.showToast('Processing is taking longer than expected. Please check back later.', 'warning');
                    }
                } else {
                    this.showInjectionStatus('❌ Failed to get task status', 'error');
                    this.showToast('Failed to monitor task progress', 'error');
                }
            } catch (error) {
                console.error('Task monitoring error:', error);
                checks++;
                if (checks < maxChecks) {
                    setTimeout(checkProgress, 5000); // Retry after 5 seconds
                } else {
                    this.showInjectionStatus('❌ Lost connection to task monitoring', 'error');
                    this.showToast('Lost connection to task monitoring', 'error');
                }
            }
        };

        // Start monitoring after a short delay
        setTimeout(checkProgress, 2000);
    }

    getProgressPercentage(request) {
        if (request.is_processed) return 100;
        if (request.is_confirmed) return 50;
        if (request.is_expired) return 0;
        return 25; // pending
    }

    // User Management Methods
    switchTab(tabName) {
        // Update tab buttons
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

        // Update tab content
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });
        document.getElementById(`${tabName}-tab`).classList.add('active');

        // Load appropriate data
        if (tabName === 'regular-users') {
            this.loadUsers();
        } else if (tabName === 'admin-users') {
            this.loadAdminUsers();
        }
    }

    async loadUsers() {
        try {
            const response = await fetch('/admin/users', {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            if (data.status === 'success') {
                this.updateUserStats(data.users);
                this.renderUsersTable(data.users);
            } else {
                this.showToast('Failed to load users', 'error');
            }
        } catch (error) {
            console.error('Error loading users:', error);
            this.showToast('Error loading users', 'error');
        }
    }

    updateUserStats(users) {
        const totalUsers = users.length;
        const activeUsers = users.filter(user => user.is_active).length;
        const usersWithUrls = users.filter(user => user.url_count > 0).length;

        document.getElementById('total-users').textContent = totalUsers;
        document.getElementById('active-users').textContent = activeUsers;
        document.getElementById('users-with-urls').textContent = usersWithUrls;
    }

    renderUsersTable(users) {
        const tbody = document.getElementById('users-tbody');

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">No users found</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => `
            <tr>
                <td>${user.full_name}</td>
                <td>${user.email}</td>
                <td>${user.phone || 'N/A'}</td>
                <td>
                    <span class="badge ${user.url_count > 0 ? 'badge-success' : 'badge-secondary'}">
                        ${user.url_count || 0}
                    </span>
                    ${user.url_count > 0 ? `<button class="btn btn-sm btn-link" onclick="adminDashboard.showUserUrls(${user.id})">View</button>` : ''}
                </td>
                <td>${this.formatDate(user.created_at)}</td>
                <td>
                    <span class="badge ${user.is_active ? 'badge-success' : 'badge-danger'}">
                        ${user.is_active ? 'Active' : 'Inactive'}
                    </span>
                </td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="adminDashboard.viewUserDetails(${user.id})">
                        <i class="fas fa-eye"></i> View
                    </button>
                    ${user.url_count > 0 ? `
                    <button class="btn btn-sm btn-primary" onclick="adminDashboard.manageUserUrls(${user.id})">
                        <i class="fas fa-globe"></i> URLs
                    </button>
                    ` : ''}
                </td>
            </tr>
        `).join('');
    }

    async manageUserUrls(userId) {
        try {
            const response = await fetch('/admin/user-urls', {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`,
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();

            if (data.status === 'success') {
                const userUrls = data.user_urls.filter(url => url.user_id === userId);
                this.showUserUrlModal(userUrls);
            } else {
                this.showToast('Failed to load user URLs', 'error');
            }
        } catch (error) {
            console.error('Error loading user URLs:', error);
            this.showToast('Error loading user URLs', 'error');
        }
    }

    showUserUrlModal(userUrls) {
        const modalHtml = `
            <div class="modal-header">
                <h3>User URL History</h3>
                <button class="modal-close" onclick="adminDashboard.closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                ${userUrls.length === 0 ? '<p>No URL requests found.</p>' :
                userUrls.map(url => `
                        <div class="url-request-item">
                            <div class="url-info">
                                <h4>${url.url}</h4>
                                <p><strong>Status:</strong> 
                                    <span class="badge badge-${url.status === 'completed' ? 'success' : url.status === 'failed' ? 'danger' : 'warning'}">
                                        ${url.status}
                                    </span>
                                </p>
                                <p><strong>Submitted:</strong> ${new Date(url.created_at).toLocaleDateString()}</p>
                                ${url.processed_at ? `<p><strong>Processed:</strong> ${new Date(url.processed_at).toLocaleDateString()}</p>` : ''}
                                ${url.description ? `<p><strong>Description:</strong> ${url.description}</p>` : ''}
                                ${url.notes ? `<p><strong>Notes:</strong> ${url.notes}</p>` : ''}
                            </div>
                        </div>
                    `).join('')
            }
            </div>
        `;

        document.getElementById('modal-container').innerHTML = modalHtml;
        document.getElementById('modal-overlay').classList.add('show');
    }

    closeModal() {
        document.getElementById('modal-overlay').classList.remove('show');
    }

    // Merge duplicate firms
    async handleMergeDuplicateFirms() {
        if (!confirm('Are you sure you want to merge duplicate firms? This action cannot be undone.')) {
            return;
        }

        try {
            this.showToast('Merging duplicate firms...', 'info');

            const response = await this.makeAuthenticatedRequest('/admin/merge-duplicate-firms', {
                method: 'POST'
            });

            const data = await response.json();

            if (data.status === 'success') {
                this.showToast(`Successfully merged ${data.merged_count} duplicate firms!`, 'success');

                // Refresh firms data and dashboard stats
                this.loadDashboardStats();

                // If we're currently viewing firms section, refresh it
                const firmsSection = document.getElementById('firms-section');
                if (firmsSection && firmsSection.classList.contains('active')) {
                    // Refresh firms table if it exists
                    console.log('Refreshing firms table...');
                }
            } else {
                this.showToast(data.message || 'Failed to merge duplicate firms', 'error');
            }
        } catch (error) {
            console.error('Error merging duplicate firms:', error);
            this.showToast('Failed to merge duplicate firms. Please try again.', 'error');
        }
    }
}

// Test function for sidebar toggle - can be called from browser console
function testSidebarToggle() {
    console.log('🧪 Testing sidebar toggle...');
    const dashboard = document.querySelector('.admin-dashboard');
    if (dashboard) {
        dashboard.classList.toggle('sidebar-collapsed');
        console.log('✅ Sidebar toggled, classes:', dashboard.classList.toString());
        return true;
    } else {
        console.error('❌ Dashboard element not found');
        return false;
    }
}

// Global function to access AdminDashboard methods
function toggleSidebarManual() {
    console.log('🔧 Manual sidebar toggle called');
    if (window.adminDashboard && window.adminDashboard.toggleSidebar) {
        window.adminDashboard.toggleSidebar();
    } else {
        console.error('❌ AdminDashboard not available, using fallback');
        testSidebarToggle(); // Fallback
    }
}

// Initialize admin dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    // Prevent multiple instances
    if (!window.adminDashboard) {
        console.log('🚀 Initializing AdminDashboard...');
        try {
            window.adminDashboard = new AdminDashboard();
            console.log('✅ AdminDashboard instantiated successfully');
        } catch (error) {
            console.error('❌ Error instantiating AdminDashboard:', error);
        }
    } else {
        console.log('⚠️ AdminDashboard already exists, skipping initialization');
    }
});

// Global functions for modal close buttons
function hideDeleteConfirmation() {
    const modal = document.getElementById('delete-confirmation-modal');
    modal.style.display = 'none';

    // Remove escape key listener if exists
    if (window.adminDashboard && window.adminDashboard.removeEscapeKeyListener) {
        window.adminDashboard.removeEscapeKeyListener();
    }
}

function hideBulkDeleteConfirmation() {
    const modal = document.getElementById('bulk-delete-confirmation-modal');
    modal.style.display = 'none';

    // Remove escape key listener if exists
    if (window.adminDashboard && window.adminDashboard.removeEscapeKeyListener) {
        window.adminDashboard.removeEscapeKeyListener();
    }
}

// Fallback for when DOMContentLoaded has already fired
if (document.readyState !== 'loading') {
    // Only create if it doesn't already exist
    if (!window.adminDashboard) {
        console.log('✅ DOM already loaded - Initializing AdminDashboard now');
        try {
            window.adminDashboard = new AdminDashboard();
            console.log('✅ AdminDashboard instantiated successfully (fallback)');
        } catch (error) {
            console.error('❌ Error instantiating AdminDashboard (fallback):', error);
        }
    } else {
        console.log('⚠️ AdminDashboard already exists, skipping fallback initialization');
    }
}
// Admin Dashboard JavaScript
class AdminDashboard {
    constructor() {
        this.authToken = localStorage.getItem('admin_token');
        this.adminInfo = JSON.parse(localStorage.getItem('admin_info') || '{}');
        this.currentSection = 'dashboard';
        
        this.init();
    }

    init() {
        // Check for OAuth callback
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has('token') && urlParams.has('admin')) {
            // Handle OAuth callback
            this.handleOAuthCallback(urlParams);
            return;
        }

        // Check authentication first
        if (this.authToken) {
            this.showDashboard();
            this.loadDashboardData();
        } else {
            this.showLogin();
        }

        this.bindEvents();
    }

    bindEvents() {
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
            link.addEventListener('click', (e) => this.handleNavigation(e));
        });

        // Sidebar toggle
        const sidebarToggle = document.getElementById('sidebar-toggle');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', () => this.toggleSidebar());
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
            selectAllUrls.addEventListener('change', (e) => this.toggleSelectAllUrls(e.target.checked));
        }

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
    }

    async handleLogin(e) {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        const errorDiv = document.getElementById('login-error');

        try {
            const response = await fetch('/admin/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (data.status === 'success') {
                this.authToken = data.token;
                this.adminInfo = data.admin;
                
                localStorage.setItem('admin_token', this.authToken);
                localStorage.setItem('admin_info', JSON.stringify(this.adminInfo));
                
                this.showDashboard();
                this.loadDashboardData();
                
                this.showToast('Login successful!', 'success');
            } else {
                errorDiv.textContent = data.message;
                errorDiv.style.display = 'block';
            }
        } catch (error) {
            console.error('Login error:', error);
            errorDiv.textContent = 'Login failed. Please try again.';
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
        e.preventDefault();
        
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
            this.authToken = null;
            this.adminInfo = {};
            
            localStorage.removeItem('admin_token');
            localStorage.removeItem('admin_info');
            
            this.showLogin();
            this.showToast('Logged out successfully', 'info');
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
        
        document.querySelector(`[data-section="${sectionName}"]`).classList.add('active');

        // Update content
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
        });
        
        document.getElementById(`${sectionName}-section`).classList.add('active');
        
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
                await this.loadAdminUsers();
                break;
        }
    }

    async loadDashboardData() {
        await this.loadDashboardStats();
        await this.loadRecentActivity();
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
        
        if (requests.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No URL requests found</td></tr>';
            return;
        }

        tbody.innerHTML = requests.map(request => `
            <tr>
                <td>
                    <input type="checkbox" class="url-checkbox" value="${request.request_id}">
                </td>
                <td>
                    <div class="url-cell">
                        <a href="${request.url}" target="_blank" title="${request.url}">
                            ${this.truncateUrl(request.url)}
                        </a>
                        ${request.firm_name ? `<br><small style="color: #666;">Firm: ${request.firm_name}</small>` : ''}
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
                    <button class="btn btn-sm btn-danger delete-contact-btn" data-id="${contact.id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');

        // Bind delete buttons
        document.querySelectorAll('.delete-contact-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const contactId = e.target.closest('button').dataset.id;
                this.deleteContact(contactId);
            });
        });
    }

    async deleteContact(contactId) {
        if (!confirm('Are you sure you want to delete this contact?')) {
            return;
        }

        try {
            const response = await this.makeAuthenticatedRequest(`/admin/contact/${contactId}`, {
                method: 'DELETE'
            });
            const data = await response.json();

            if (data.status === 'success') {
                this.showToast('Contact deleted successfully!', 'success');
                this.loadContacts(); // Refresh the table
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
                <td>
                    <button class="btn btn-sm btn-secondary" disabled>
                        <i class="fas fa-cog"></i> Manage
                    </button>
                </td>
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
    }

    showDashboard() {
        document.getElementById('loading-overlay').style.display = 'none';
        document.getElementById('admin-login').style.display = 'none';
        document.getElementById('admin-dashboard').style.display = 'block';
        
        // Update admin name
        const adminNameEl = document.getElementById('admin-name');
        if (adminNameEl) {
            adminNameEl.textContent = this.adminInfo.full_name || this.adminInfo.username;
        }
    }

    toggleSidebar() {
        const sidebar = document.getElementById('admin-sidebar');
        sidebar.classList.toggle('open');
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

        if (request.is_confirmed && !request.is_processed && !request.is_expired) {
            buttons += `
                <button class="btn btn-sm btn-success process-url-btn" data-request-id="${request.request_id}">
                    <i class="fas fa-cogs"></i> Process
                </button>
            `;
        }

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
                this.showInjectionStatus(`✅ ${data.message}`, 'success');
                this.showToast('URL successfully injected and processed!', 'success');
                
                // Clear form after short delay
                setTimeout(() => {
                    this.hideUrlInjectionForm();
                    this.loadUrlRequests(); // Refresh URL requests table
                    this.loadDashboardStats(); // Refresh dashboard stats
                }, 2000);
                
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

    getProgressPercentage(request) {
        if (request.is_processed) return 100;
        if (request.is_confirmed) return 50;
        if (request.is_expired) return 0;
        return 25; // pending
    }
}

// Initialize admin dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.adminDashboard = new AdminDashboard();
});
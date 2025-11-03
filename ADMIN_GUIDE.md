# 🛡️ Admin Dashboard for Web Assistant

A comprehensive admin panel for managing URL injections, user data, and system operations.

## 🚀 Features

### 🔐 **Secure Authentication**
- **Session-based authentication** with secure tokens
- **Role-based access control** (Admin/Super Admin)
- **Automatic session expiration** (24 hours)
- **Secure password hashing** using SHA256

### 📊 **Dashboard Overview**
- **Real-time statistics** for URLs, contacts, and firms
- **Recent activity monitoring** 
- **System health indicators**
- **Quick action buttons**

### 🔗 **URL Management**
- **View all URL injection requests** with filtering
- **Process confirmed URLs** individually or in bulk
- **Status tracking** (Pending, Confirmed, Processed, Expired)
- **Email confirmation oversight**

### 👥 **User Management** 
- **Contact management** with export capabilities
- **Admin user administration**
- **Firm and website oversight**
- **Data deletion and cleanup tools**

### 📈 **System Monitoring**
- **Real-time data updates**
- **Activity logging**
- **Error tracking and debugging**
- **Performance metrics**

## 🔧 Installation & Setup

### 1. Environment Configuration

Add these variables to your `.env` file:

```bash
# Admin Panel Configuration
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
ADMIN_EMAIL=admin@yourdomain.com

# Database and Email configs (existing)
SMTP_HOST=smtp.gmail.com
SMTP_USER=your-email@gmail.com
# ... other existing configs
```

### 2. Database Initialization

The admin tables are created automatically when you start the server:

```bash
python mains.py
```

The system will:
- ✅ Create admin database tables
- ✅ Initialize default admin user
- ✅ Set up session management

### 3. Access the Admin Panel

Navigate to: **http://127.0.0.1:8000/admin**

**Default credentials:**
- Username: `admin`
- Password: `admin123`

> ⚠️ **Change these credentials immediately after first login!**

## 🎯 Admin Panel Sections

### 📊 **Dashboard**
- **Statistics Cards**: Total URLs, pending requests, contacts, firms
- **Recent Activity**: Latest URL requests and contact submissions
- **Quick Actions**: Bulk operations and system controls

### 🔗 **URL Management**
- **Request Table**: All URL injection requests with status
- **Filtering**: By status (pending, confirmed, processed, expired)
- **Actions**: 
  - Process individual URLs
  - Bulk process all confirmed URLs
  - View original URLs
  - Monitor email confirmations

### 👥 **User Management**
- **Contact List**: All submitted contact forms
- **Export Options**: Download contact data
- **Admin Users**: Manage admin accounts and permissions
- **Delete Operations**: Clean up old or invalid data

### 🏢 **Firms Management**
- **Firm Directory**: All registered firms
- **Website Counts**: Number of websites per firm
- **Firm Details**: Creation dates and statistics

### 📁 **System Logs**
- **Real-time Logs**: System events and errors
- **Debug Information**: Detailed operation tracking
- **Log Management**: Clear and export capabilities

## 🔑 Admin Operations

### **URL Injection Workflow**

1. **Monitor Requests**: View all pending URL requests
2. **Email Verification**: Ensure requests are properly confirmed
3. **Process URLs**: Convert confirmed requests to knowledge base entries
4. **Bulk Operations**: Process multiple URLs simultaneously

### **User Data Management**

1. **Contact Oversight**: Review submitted contact forms
2. **Data Export**: Download user data for analysis
3. **Cleanup Operations**: Remove outdated or invalid entries
4. **Privacy Compliance**: Manage data retention policies

### **System Administration**

1. **Monitor Statistics**: Track system usage and performance
2. **Manage Access**: Control admin user permissions
3. **Debug Issues**: Access detailed system logs
4. **Maintain Data**: Regular cleanup and optimization

## 🔒 Security Features

### **Authentication Security**
- **Secure token generation** using `secrets.token_urlsafe(32)`
- **Session-based authentication** with automatic expiration
- **Password hashing** with SHA256 algorithm
- **Authorization middleware** for all admin endpoints

### **Access Control**
- **Role-based permissions** (Admin vs Super Admin)
- **Session validation** on every request
- **Automatic logout** on token expiration
- **CSRF protection** through token validation

### **Data Protection**
- **Input validation** on all admin operations
- **SQL injection prevention** through SQLAlchemy ORM
- **XSS protection** through proper data sanitization
- **Rate limiting** on sensitive operations

## 🎨 User Interface

### **Modern Design**
- **Responsive layout** works on desktop and mobile
- **Professional styling** with clean, intuitive interface
- **Real-time updates** without page refreshes
- **Toast notifications** for user feedback

### **Navigation**
- **Sidebar navigation** with section switching
- **Breadcrumb navigation** for complex workflows
- **Quick actions** accessible from dashboard
- **Search and filtering** for large datasets

### **Data Tables**
- **Sortable columns** for easy data organization
- **Pagination** for large datasets
- **Bulk operations** with select-all functionality
- **Action buttons** for quick operations

## 📡 API Endpoints

### **Authentication**
```bash
POST /admin/login          # Admin login
POST /admin/logout         # Admin logout
```

### **Dashboard Data**
```bash
GET /admin/stats           # System statistics
GET /admin/url-requests    # URL injection requests
GET /admin/contacts        # Contact submissions
GET /admin/firms           # Firm listings
```

### **Operations**
```bash
POST /admin/process-url/{id}      # Process single URL
POST /admin/bulk-process-urls     # Process all confirmed URLs
DELETE /admin/contact/{id}        # Delete contact
```

## 🔧 Customization

### **Styling**
Modify `/static/css/admin.css` for:
- Color schemes and branding
- Layout adjustments
- Component styling
- Responsive breakpoints

### **Functionality**
Extend `/static/js/admin.js` for:
- Additional admin operations
- Custom data processing
- Enhanced user interactions
- Real-time notifications

### **Backend**
Modify admin endpoints in `mains.py` for:
- Additional data access
- Custom business logic
- Enhanced security measures
- Performance optimizations

## 🐛 Troubleshooting

### **Common Issues**

**Login Problems:**
```bash
# Check admin user exists
python -c "from utils.admin_auth_service import admin_auth_service; admin_auth_service.initialize_default_admin()"

# Verify credentials in .env
echo $ADMIN_USERNAME
echo $ADMIN_PASSWORD
```

**Permission Errors:**
```bash
# Check session token
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/admin/stats

# Clear expired sessions
# Restart the server to reset all sessions
```

**Data Loading Issues:**
```bash
# Check database connections
python -c "from database.db import SessionLocal; db = SessionLocal(); print('DB connected')"

# Verify admin tables exist
python -c "from model.admin_models import AdminUser; print('Admin models loaded')"
```

### **Debug Mode**

Enable debug logging by adding to your environment:
```bash
DEBUG_MODE=true
LOG_LEVEL=DEBUG
```

## 📚 Development

### **Adding New Features**

1. **Backend**: Add new endpoints in `mains.py`
2. **Frontend**: Add UI components in `admin.html`
3. **Styling**: Update `admin.css` for new components
4. **Logic**: Extend `admin.js` for new functionality

### **Database Changes**

1. **Models**: Update `admin_models.py` for new tables
2. **Migration**: Add to `init_db()` in `database/db.py`
3. **API**: Create endpoints for new data operations
4. **UI**: Add interface components for new features

## 🔄 Updates & Maintenance

### **Regular Tasks**
- **Monitor system logs** for errors or issues
- **Review URL requests** for spam or invalid submissions
- **Clean up old data** to maintain performance
- **Update admin passwords** periodically

### **System Health**
- **Check database performance** with large datasets
- **Monitor email delivery** for URL confirmations
- **Verify backup procedures** for data protection
- **Test admin functionality** after updates

---

## 🎯 Quick Start Checklist

- [ ] Configure `.env` with admin credentials
- [ ] Start the server and verify database initialization
- [ ] Access admin panel at `/admin`
- [ ] Change default admin password
- [ ] Test URL injection workflow
- [ ] Verify contact management functionality
- [ ] Review system statistics and logs

**Your admin dashboard is now ready! 🚀**

Access it at: **http://127.0.0.1:8000/admin**
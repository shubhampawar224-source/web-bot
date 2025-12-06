# Production Deployment Guide
## Domain: chatbot.thedjflawfirm.com

### Deployment Information
- **Server IP**: 3.135.153.94
- **Domain**: chatbot.thedjflawfirm.com
- **SSL Certificate**: Let's Encrypt (Auto-renews)
- **Certificate Expires**: 2026-03-01
- **Web Server**: Nginx (Reverse Proxy)
- **Application**: FastAPI (Docker Container)
- **Application Port**: 8000 (localhost only)
- **Public Ports**: 80 (HTTP) → redirects to 443 (HTTPS)

### Architecture
```
Internet → Cloudflare (SSL: Full) → Nginx (Port 443) → FastAPI Container (Port 8000)
```

### Configuration Files
1. **Nginx Config**: `/etc/nginx/sites-available/chatbot.thedjflawfirm.com`
2. **Docker Compose**: `/home/ubuntu/web-bot/docker-compose.yaml`
3. **Environment**: `/home/ubuntu/web-bot/.env`
4. **SSL Certificates**: `/etc/letsencrypt/live/chatbot.thedjflawfirm.com/`

### Key Configuration Details

#### Cloudflare Settings
- **DNS A Record**: chatbot.thedjflawfirm.com → 3.135.153.94
- **SSL/TLS Mode**: Full (encrypts traffic between Cloudflare and origin server)
- **Proxy Status**: Should be enabled (orange cloud)

#### Nginx Configuration
- Listens on ports 80 (redirects to 443) and 443 (HTTPS)
- Reverse proxies to FastAPI on localhost:8000
- Includes WebSocket support for real-time features
- Rate limiting: 10 requests/second with burst of 20
- Max upload size: 50MB (for voice files)
- Gzip compression enabled
- Static file caching: 30 days

#### Docker Container
- Container name: `web-assistant`
- Port binding: `127.0.0.1:8000:8000` (localhost only for security)
- Restart policy: always
- Volume mount: Current directory to /app

### Important URLs
- **Main Application**: https://chatbot.thedjflawfirm.com
- **Admin Panel**: https://chatbot.thedjflawfirm.com/admin.html
- **Widget Embed**: https://chatbot.thedjflawfirm.com/static/embed-script.js

### Deployment Commands

#### Start/Restart Application
```bash
cd /home/ubuntu/web-bot
sudo docker-compose down
sudo docker-compose up -d --build
```

#### Check Application Status
```bash
# Check container status
sudo docker ps | grep web-assistant

# View container logs
sudo docker logs web-assistant -f

# Check Nginx status
sudo systemctl status nginx

# View Nginx logs
sudo tail -f /var/log/nginx/chatbot.thedjflawfirm.com.access.log
sudo tail -f /var/log/nginx/chatbot.thedjflawfirm.com.error.log
```

#### Nginx Commands
```bash
# Test Nginx configuration
sudo nginx -t

# Reload Nginx (without downtime)
sudo systemctl reload nginx

# Restart Nginx
sudo systemctl restart nginx

# View Nginx configuration
sudo cat /etc/nginx/sites-available/chatbot.thedjflawfirm.com
```

#### SSL Certificate Management
```bash
# Check certificate expiry
sudo certbot certificates

# Manually renew certificate (auto-renewal is configured)
sudo certbot renew

# Test certificate renewal
sudo certbot renew --dry-run
```

### Security Features
1. **HTTPS Only**: All HTTP traffic redirects to HTTPS
2. **Cloudflare Protection**: DDoS protection and Web Application Firewall
3. **Rate Limiting**: Prevents API abuse
4. **Localhost Binding**: Application only accessible via Nginx
5. **Security Headers**: 
   - X-Content-Type-Options
   - X-XSS-Protection
   - Referrer-Policy
   - HSTS (HTTP Strict Transport Security)

### CORS Configuration
The application is configured to:
- Allow embedding in iframes (for widget functionality)
- Support CORS for cross-origin requests
- Handle preflight OPTIONS requests
- Allow credentials in cross-origin requests

### Monitoring & Maintenance

#### Regular Checks
1. **Certificate Expiry**: Check monthly (auto-renews at 30 days before expiry)
2. **Disk Space**: Monitor `/var/log/nginx/` and Docker volumes
3. **Container Health**: Ensure container stays running
4. **Nginx Logs**: Review for errors or unusual traffic patterns

#### Backup Important Files
- `/home/ubuntu/web-bot/.env` (contains secrets)
- `/home/ubuntu/web-bot/docker-compose.yaml`
- `/etc/nginx/sites-available/chatbot.thedjflawfirm.com`
- Database files (if using SQLite)

### Troubleshooting

#### Application Not Responding
```bash
# Restart Docker container
cd /home/ubuntu/web-bot
sudo docker-compose restart

# Check application logs
sudo docker logs web-assistant --tail 100
```

#### SSL Certificate Issues
```bash
# Check certificate status
sudo certbot certificates

# Manually renew
sudo certbot renew --nginx
```

#### Nginx Issues
```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log

# Restart Nginx
sudo systemctl restart nginx
```

#### Connection Issues
```bash
# Check if ports are open
sudo netstat -tlnp | grep -E ':(80|443|8000)'

# Check firewall rules
sudo ufw status

# Verify Docker container is running
sudo docker ps -a | grep web-assistant
```

### Environment Variables
Key environment variables in `.env`:
- `WIDGET_BASE_URL`: https://chatbot.thedjflawfirm.com/
- `GOOGLE_REDIRECT_URI`: https://chatbot.thedjflawfirm.com/admin/oauth/callback
- `OPENAI_API_KEY`: Configured
- `DATABASE_URL`: SQLite database location

### Next Steps After Deployment
1. ✅ Test HTTPS access: https://chatbot.thedjflawfirm.com
2. ✅ Verify SSL certificate is valid
3. ✅ Test widget embedding on external sites
4. ✅ Update Google OAuth credentials (if using OAuth)
5. ✅ Update Cloudflare SSL settings to "Full"
6. ✅ Configure any additional Cloudflare rules as needed
7. ✅ Test chatbot functionality
8. ✅ Monitor logs for any issues

### Contact & Support
- Server: AWS EC2 (us-east-2)
- Domain Registrar: Configured with Cloudflare
- SSL Provider: Let's Encrypt (Free, Auto-renewing)

---
**Last Updated**: December 1, 2025
**Deployed By**: Automated deployment script

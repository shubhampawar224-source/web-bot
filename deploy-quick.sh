#!/bin/bash
# Quick Deployment Script for chatbot.thedjflawfirm.com
# Usage: ./deploy-quick.sh [command]

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

case "${1:-deploy}" in
    deploy)
        echo "🚀 Deploying application..."
        sudo docker-compose down
        sudo docker-compose up -d --build
        echo "✅ Application deployed!"
        echo "📊 Checking status..."
        sudo docker ps | grep web-assistant
        ;;
    
    restart)
        echo "🔄 Restarting application..."
        sudo docker-compose restart
        echo "✅ Application restarted!"
        ;;
    
    stop)
        echo "🛑 Stopping application..."
        sudo docker-compose down
        echo "✅ Application stopped!"
        ;;
    
    start)
        echo "▶️  Starting application..."
        sudo docker-compose up -d
        echo "✅ Application started!"
        ;;
    
    logs)
        echo "📋 Showing application logs (Ctrl+C to exit)..."
        sudo docker logs web-assistant -f
        ;;
    
    status)
        echo "📊 Application Status:"
        echo "-------------------"
        sudo docker ps | grep web-assistant || echo "❌ Container not running"
        echo ""
        echo "🌐 Nginx Status:"
        echo "-------------------"
        sudo systemctl status nginx --no-pager | head -5
        echo ""
        echo "🔒 SSL Certificate:"
        echo "-------------------"
        sudo certbot certificates | grep -A 5 "chatbot.thedjflawfirm.com" || echo "No certificate found"
        ;;
    
    nginx-reload)
        echo "🔄 Reloading Nginx configuration..."
        sudo nginx -t && sudo systemctl reload nginx
        echo "✅ Nginx reloaded!"
        ;;
    
    nginx-logs)
        echo "📋 Showing Nginx logs (Ctrl+C to exit)..."
        sudo tail -f /var/log/nginx/chatbot.thedjflawfirm.com.access.log
        ;;
    
    ssl-renew)
        echo "🔒 Renewing SSL certificate..."
        sudo certbot renew
        echo "✅ SSL certificate renewed!"
        ;;
    
    test)
        echo "🧪 Testing deployment..."
        echo ""
        echo "1. Testing local application..."
        LOCAL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
        if [ "$LOCAL_STATUS" = "200" ]; then
            echo "   ✅ Local application: OK ($LOCAL_STATUS)"
        else
            echo "   ❌ Local application: FAILED ($LOCAL_STATUS)"
        fi
        
        echo ""
        echo "2. Testing HTTPS domain..."
        HTTPS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://chatbot.thedjflawfirm.com/)
        if [ "$HTTPS_STATUS" = "200" ]; then
            echo "   ✅ HTTPS domain: OK ($HTTPS_STATUS)"
        else
            echo "   ❌ HTTPS domain: FAILED ($HTTPS_STATUS)"
        fi
        
        echo ""
        echo "3. Testing SSL certificate..."
        SSL_DATES=$(echo | openssl s_client -servername chatbot.thedjflawfirm.com -connect chatbot.thedjflawfirm.com:443 2>/dev/null | openssl x509 -noout -dates 2>/dev/null || echo "Failed")
        if [ "$SSL_DATES" != "Failed" ]; then
            echo "   ✅ SSL certificate: Valid"
            echo "      $SSL_DATES"
        else
            echo "   ❌ SSL certificate: Check failed"
        fi
        
        echo ""
        echo "4. Checking container health..."
        if sudo docker ps | grep -q web-assistant; then
            echo "   ✅ Container: Running"
        else
            echo "   ❌ Container: Not running"
        fi
        ;;
    
    update-env)
        echo "📝 Current environment settings:"
        echo "-------------------"
        grep -E "^WIDGET_BASE_URL|^GOOGLE_REDIRECT_URI" .env || echo "Settings not found"
        echo ""
        echo "ℹ️  To update environment variables, edit the .env file and run: ./deploy-quick.sh restart"
        ;;
    
    help|*)
        echo "📚 Deployment Script Commands:"
        echo "------------------------------"
        echo "  deploy         - Deploy/redeploy the application (default)"
        echo "  restart        - Restart the application"
        echo "  stop           - Stop the application"
        echo "  start          - Start the application"
        echo "  logs           - View application logs"
        echo "  status         - Show application, Nginx, and SSL status"
        echo "  nginx-reload   - Reload Nginx configuration"
        echo "  nginx-logs     - View Nginx access logs"
        echo "  ssl-renew      - Manually renew SSL certificate"
        echo "  test           - Run deployment tests"
        echo "  update-env     - Show current environment settings"
        echo "  help           - Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./deploy-quick.sh deploy"
        echo "  ./deploy-quick.sh logs"
        echo "  ./deploy-quick.sh test"
        ;;
esac

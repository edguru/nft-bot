#!/bin/bash

# NFT Minting Bot - Automated Deployment Script
# This script automates the entire deployment process on AWS EC2

set -e  # Exit on any error

echo "=========================================="
echo "NFT Minting Bot - Deployment Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check if running on EC2
check_environment() {
    print_info "Checking environment..."
    
    if [ -f /sys/hypervisor/uuid ] && [ `head -c 3 /sys/hypervisor/uuid` == "ec2" ]; then
        print_success "Running on AWS EC2"
    else
        print_info "Not running on EC2 - proceeding anyway"
    fi
}

# Collect user inputs
collect_inputs() {
    echo ""
    echo "Please provide the following information:"
    echo ""
    
    read -p "AWS Region (default: us-east-1): " AWS_REGION
    AWS_REGION=${AWS_REGION:-us-east-1}
    
    read -p "SNS Topic ARN: " SNS_TOPIC_ARN
    read -p "Email for notifications: " EMAIL_RECIPIENT
    read -p "S3 Bucket name (default: nft-minting-bot-data): " S3_BUCKET
    S3_BUCKET=${S3_BUCKET:-nft-minting-bot-data}
    
    read -p "Secrets Manager secret name (default: nft-bot-owner-key): " SECRET_NAME
    SECRET_NAME=${SECRET_NAME:-nft-bot-owner-key}
    
    echo ""
    print_info "Configuration Summary:"
    echo "  AWS Region: $AWS_REGION"
    echo "  SNS Topic: $SNS_TOPIC_ARN"
    echo "  Email: $EMAIL_RECIPIENT"
    echo "  S3 Bucket: $S3_BUCKET"
    echo "  Secret Name: $SECRET_NAME"
    echo ""
    
    read -p "Continue with deployment? (y/n): " CONFIRM
    if [ "$CONFIRM" != "y" ]; then
        print_error "Deployment cancelled"
        exit 1
    fi
}

# Install system dependencies
install_dependencies() {
    print_info "Installing system dependencies..."
    
    # Detect OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        print_error "Cannot detect OS"
        exit 1
    fi
    
    if [ "$OS" == "amzn" ] || [ "$OS" == "rhel" ]; then
        # Amazon Linux / RHEL
        sudo yum update -y
        sudo yum install -y python3.11 python3.11-pip nginx git
    elif [ "$OS" == "ubuntu" ] || [ "$OS" == "debian" ]; then
        # Ubuntu / Debian
        sudo apt update
        sudo apt install -y python3.11 python3-pip nginx git
    else
        print_error "Unsupported OS: $OS"
        exit 1
    fi
    
    print_success "System dependencies installed"
}

# Setup project directory
setup_project() {
    print_info "Setting up project directory..."
    
    PROJECT_DIR="$HOME/nft-bot"
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"
    
    print_success "Project directory created: $PROJECT_DIR"
}

# Install Python dependencies
install_python_deps() {
    print_info "Installing Python dependencies..."
    
    cd "$PROJECT_DIR"
    python3.11 -m pip install --upgrade pip
    python3.11 -m pip install -r requirements.txt
    
    print_success "Python dependencies installed"
}

# Configure environment variables
configure_environment() {
    print_info "Configuring environment variables..."
    
    # Create environment file
    cat > "$PROJECT_DIR/.env" << EOF
AWS_DEFAULT_REGION=$AWS_REGION
SNS_TOPIC_ARN=$SNS_TOPIC_ARN
EMAIL_RECIPIENT=$EMAIL_RECIPIENT
S3_BUCKET=$S3_BUCKET
SECRET_NAME=$SECRET_NAME
EOF
    
    # Add to system environment
    if ! grep -q "AWS_DEFAULT_REGION" /etc/environment; then
        echo "export AWS_DEFAULT_REGION=$AWS_REGION" | sudo tee -a /etc/environment
        echo "export SNS_TOPIC_ARN=$SNS_TOPIC_ARN" | sudo tee -a /etc/environment
        echo "export EMAIL_RECIPIENT=$EMAIL_RECIPIENT" | sudo tee -a /etc/environment
        echo "export S3_BUCKET=$S3_BUCKET" | sudo tee -a /etc/environment
        echo "export SECRET_NAME=$SECRET_NAME" | sudo tee -a /etc/environment
    fi
    
    # Load environment
    export AWS_DEFAULT_REGION=$AWS_REGION
    export SNS_TOPIC_ARN=$SNS_TOPIC_ARN
    export EMAIL_RECIPIENT=$EMAIL_RECIPIENT
    export S3_BUCKET=$S3_BUCKET
    export SECRET_NAME=$SECRET_NAME
    
    print_success "Environment configured"
}

# Create systemd services
create_services() {
    print_info "Creating systemd services..."
    
    # API Service
    sudo tee /etc/systemd/system/nft-api.service > /dev/null << EOF
[Unit]
Description=NFT Bot API Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
Environment="AWS_DEFAULT_REGION=$AWS_REGION"
Environment="SNS_TOPIC_ARN=$SNS_TOPIC_ARN"
Environment="EMAIL_RECIPIENT=$EMAIL_RECIPIENT"
Environment="S3_BUCKET=$S3_BUCKET"
Environment="SECRET_NAME=$SECRET_NAME"
ExecStart=/usr/bin/python3.11 $PROJECT_DIR/api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable nft-api
    
    print_success "Systemd services created"
}

# Configure Nginx
configure_nginx() {
    print_info "Configuring Nginx..."
    
    # Get server IP
    SERVER_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "localhost")
    
    sudo tee /etc/nginx/conf.d/nft-bot.conf > /dev/null << EOF
server {
    listen 80;
    server_name $SERVER_IP _;

    location / {
        root $PROJECT_DIR;
        index index.html;
        try_files \$uri \$uri/ =404;
    }

    location /api/ {
        proxy_pass http://localhost:5000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
    
    # Test nginx config
    sudo nginx -t
    
    # Start nginx
    sudo systemctl enable nginx
    sudo systemctl restart nginx
    
    print_success "Nginx configured"
}

# Setup firewall
setup_firewall() {
    print_info "Configuring firewall..."
    
    # Check if firewalld is available
    if command -v firewall-cmd &> /dev/null; then
        sudo firewall-cmd --permanent --add-service=http
        sudo firewall-cmd --permanent --add-service=https
        sudo firewall-cmd --reload
        print_success "Firewall configured (firewalld)"
    elif command -v ufw &> /dev/null; then
        sudo ufw allow 80/tcp
        sudo ufw allow 443/tcp
        print_success "Firewall configured (ufw)"
    else
        print_info "No firewall detected - skipping"
    fi
}

# Test AWS connectivity
test_aws() {
    print_info "Testing AWS connectivity..."
    
    # Test AWS credentials
    if python3.11 -c "import boto3; boto3.client('sts').get_caller_identity()" 2>/dev/null; then
        print_success "AWS credentials valid"
    else
        print_error "AWS credentials not configured"
        print_info "Please configure IAM role on EC2 instance"
        return 1
    fi
    
    # Test Secrets Manager
    if python3.11 -c "import boto3,json; boto3.client('secretsmanager').get_secret_value(SecretId='$SECRET_NAME')" 2>/dev/null; then
        print_success "Secrets Manager accessible"
    else
        print_error "Cannot access secret: $SECRET_NAME"
        return 1
    fi
    
    # Test S3
    if aws s3 ls s3://$S3_BUCKET 2>/dev/null; then
        print_success "S3 bucket accessible"
    else
        print_error "Cannot access S3 bucket: $S3_BUCKET"
        print_info "Creating bucket..."
        aws s3 mb s3://$S3_BUCKET --region $AWS_REGION || true
    fi
}

# Start services
start_services() {
    print_info "Starting services..."
    
    sudo systemctl start nft-api
    sudo systemctl status nft-api --no-pager
    
    print_success "Services started"
}

# Display final information
show_completion() {
    SERVER_IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 || echo "localhost")
    
    echo ""
    echo "=========================================="
    echo -e "${GREEN}Deployment Complete!${NC}"
    echo "=========================================="
    echo ""
    echo "Access your dashboard at:"
    echo -e "  ${GREEN}http://$SERVER_IP${NC}"
    echo ""
    echo "Useful commands:"
    echo "  View API logs:    sudo journalctl -u nft-api -f"
    echo "  View bot logs:    tail -f $PROJECT_DIR/bot.log"
    echo "  Restart API:      sudo systemctl restart nft-api"
    echo "  Stop API:         sudo systemctl stop nft-api"
    echo ""
    echo "Next steps:"
    echo "  1. Open dashboard in browser"
    echo "  2. Click 'Start Bot' to begin minting"
    echo "  3. Monitor transactions and logs"
    echo ""
    echo "=========================================="
}

# Main deployment flow
main() {
    check_environment
    collect_inputs
    install_dependencies
    setup_project
    install_python_deps
    configure_environment
    create_services
    configure_nginx
    setup_firewall
    
    if test_aws; then
        start_services
        show_completion
    else
        print_error "AWS configuration failed"
        print_info "Please fix AWS issues and run: sudo systemctl start nft-api"
    fi
}

# Run main function
main

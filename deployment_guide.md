# NFT Minting Bot - Complete Deployment Guide

## 📋 Project Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         AWS Cloud                            │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐ │
│  │  EC2 Instance│    │   S3 Bucket  │    │  AWS SNS     │ │
│  │              │───▶│  (Backups)   │    │  (Alerts)    │ │
│  │  Bot + API   │    └──────────────┘    └──────────────┘ │
│  │  + Frontend  │                                          │
│  └──────┬───────┘    ┌──────────────┐    ┌──────────────┐ │
│         │            │ Secrets Mgr  │    │   AWS SES    │ │
│         └───────────▶│ (Owner Key)  │    │  (Email)     │ │
│                      └──────────────┘    └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌──────────────────┐
                    │  Avalanche       │
                    │  Mainnet/Testnet │
                    │  (Smart Contracts)│
                    └──────────────────┘
```

## 📦 Project Structure

```
nft-minting-bot/
├── bot.py                      # Main minting bot
├── api.py                      # Flask API server
├── requirements.txt            # Python dependencies
├── index.html                  # Dashboard frontend
├── deploy.sh                   # Deployment script
├── systemd/
│   ├── bot.service            # Bot systemd service
│   └── api.service            # API systemd service
├── nginx/
│   └── nft-bot.conf           # Nginx configuration
└── README.md                   # This file
```

## 🚀 Step-by-Step Deployment

### Step 1: AWS Account Setup

#### 1.1 Create IAM User with Required Permissions
```bash
# Required AWS Services:
- EC2 (Launch and manage instances)
- S3 (Store backups)
- SNS (Send alerts)
- SES (Send emails)
- Secrets Manager (Store private key)
```

Create IAM policy with these permissions:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::nft-minting-bot-data",
        "arn:aws:s3:::nft-minting-bot-data/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
```

#### 1.2 Create S3 Bucket
```bash
aws s3 mb s3://nft-minting-bot-data --region us-east-1
```

#### 1.3 Setup AWS SNS
```bash
# Create SNS topic
aws sns create-topic --name nft-bot-alerts --region us-east-1

# Subscribe your email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:nft-bot-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com

# Confirm subscription via email
```

#### 1.4 Setup AWS SES
```bash
# Verify your email address
aws ses verify-email-identity \
  --email-address your-email@example.com \
  --region us-east-1

# Check verification status
aws ses get-identity-verification-attributes \
  --identities your-email@example.com \
  --region us-east-1

# Note: For production, request SES production access
```

#### 1.5 Store Owner Private Key in Secrets Manager
```bash
# Create secret with owner's private key
aws secretsmanager create-secret \
  --name nft-bot-owner-key \
  --description "Owner wallet private key for NFT minting bot" \
  --secret-string '{"private_key":"0xYOUR_PRIVATE_KEY_HERE"}' \
  --region us-east-1
```

### Step 2: Launch EC2 Instance

#### 2.1 Launch Instance
```bash
# Recommended: t3.small or t3.medium
# OS: Amazon Linux 2023 or Ubuntu 22.04
# Storage: 20GB SSD
# Security Group: Allow ports 22 (SSH), 80 (HTTP), 5000 (API)
```

Launch via AWS Console or CLI:
```bash
aws ec2 run-instances \
  --image-id ami-xxxxxxxxx \
  --instance-type t3.small \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx \
  --subnet-id subnet-xxxxxxxx \
  --iam-instance-profile Name=nft-bot-role \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=nft-bot}]'
```

#### 2.2 Attach IAM Role to EC2
Create an IAM role with the policy from Step 1.1 and attach it to your EC2 instance.

### Step 3: Server Setup

#### 3.1 SSH into EC2
```bash
ssh -i your-key.pem ec2-user@your-ec2-ip
```

#### 3.2 Install Dependencies
```bash
# Update system
sudo yum update -y

# Install Python 3.11
sudo yum install python3.11 python3.11-pip -y

# Install Nginx
sudo yum install nginx -y

# Install Git
sudo yum install git -y
```

#### 3.3 Clone/Upload Project
```bash
# Create project directory
mkdir -p ~/nft-bot
cd ~/nft-bot

# Upload your files (using scp from local machine)
# Or create files manually
```

Upload files from your local machine:
```bash
# From your local machine
scp -i your-key.pem bot.py api.py requirements.txt index.html ec2-user@your-ec2-ip:~/nft-bot/
```

#### 3.4 Install Python Dependencies
```bash
cd ~/nft-bot
python3.11 -m pip install -r requirements.txt
```

### Step 4: Environment Configuration

#### 4.1 Set Environment Variables
```bash
# Create environment file
sudo nano /etc/environment

# Add these lines:
export AWS_DEFAULT_REGION=us-east-1
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:nft-bot-alerts
export EMAIL_RECIPIENT=your-email@example.com
export S3_BUCKET=nft-minting-bot-data
export SECRET_NAME=nft-bot-owner-key

# Load environment
source /etc/environment
```

### Step 5: Setup Systemd Services

#### 5.1 Create Bot Service
```bash
sudo nano /etc/systemd/system/nft-bot.service
```

```ini
[Unit]
Description=NFT Minting Bot
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/nft-bot
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/etc/environment
ExecStart=/usr/bin/python3.11 /home/ec2-user/nft-bot/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 5.2 Create API Service
```bash
sudo nano /etc/systemd/system/nft-api.service
```

```ini
[Unit]
Description=NFT Bot API Server
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/home/ec2-user/nft-bot
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/etc/environment
ExecStart=/usr/bin/python3.11 /home/ec2-user/nft-bot/api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

#### 5.3 Enable Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable nft-api
sudo systemctl start nft-api
sudo systemctl status nft-api

# Don't start bot yet - use dashboard to control it
```

### Step 6: Setup Nginx

#### 6.1 Configure Nginx
```bash
sudo nano /etc/nginx/conf.d/nft-bot.conf
```

```nginx
server {
    listen 80;
    server_name your-domain.com;  # or use IP address

    # Frontend
    location / {
        root /home/ec2-user/nft-bot;
        index index.html;
        try_files $uri $uri/ =404;
    }

    # API Proxy
    location /api/ {
        proxy_pass http://localhost:5000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

#### 6.2 Start Nginx
```bash
sudo systemctl start nginx
sudo systemctl enable nginx
sudo systemctl status nginx
```

#### 6.3 Configure Firewall
```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### Step 7: Testing

#### 7.1 Test API
```bash
curl http://localhost:5000/health
```

Expected response:
```json
{"status":"healthy","timestamp":"2024-XX-XX..."}
```

#### 7.2 Test Dashboard
Open browser: `http://your-ec2-ip`

You should see the dashboard with:
- Bot status indicator
- Start/Stop buttons
- Statistics (all zeros initially)
- Wallet balances

#### 7.3 Test Bot Start
1. Click "Start Bot" in dashboard
2. Check logs in dashboard
3. Verify alerts are received via email/SNS

### Step 8: Monitoring & Maintenance

#### 8.1 View Logs
```bash
# API logs
sudo journalctl -u nft-api -f

# Bot logs
tail -f ~/nft-bot/bot.log

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

#### 8.2 Daily Maintenance Script
Create a cron job for daily backups:

```bash
crontab -e

# Add this line (runs daily at 2 AM)
0 2 * * * cd ~/nft-bot && python3.11 -c "import boto3; s3=boto3.client('s3'); s3.upload_file('nft_minting_records.csv', 'nft-minting-bot-data', 'daily_backup_$(date +\%Y\%m\%d).csv')"
```

### Step 9: Security Hardening

#### 9.1 SSL Certificate (Optional but Recommended)
```bash
# Install Certbot
sudo yum install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d your-domain.com
```

#### 9.2 Update Security Group
- Limit SSH (port 22) to your IP only
- Allow HTTP/HTTPS from anywhere
- Keep port 5000 closed to public (Nginx proxies it)

#### 9.3 Regular Updates
```bash
# Create update script
cat > ~/update.sh << 'EOF'
#!/bin/bash
sudo yum update -y
python3.11 -m pip install --upgrade pip
python3.11 -m pip install --upgrade -r ~/nft-bot/requirements.txt
sudo systemctl restart nft-api
EOF

chmod +x ~/update.sh
```

## 🎯 Usage Guide

### Starting the Bot
1. Open dashboard at `http://your-ec2-ip`
2. Click "Start Bot"
3. Monitor logs and transactions in real-time

### Stopping the Bot
1. Click "Stop Bot" in dashboard
2. Bot will finish current transaction and stop
3. Final report will be emailed

### Exporting Data
- **Download CSV**: Click "Download CSV" button
- **Email CSV**: Click "Email CSV" button

### Monitoring
- **Dashboard**: Real-time stats and logs
- **Email Alerts**: Low gas, failures, start/stop
- **SNS Notifications**: Critical alerts
- **S3 Backups**: Automatic daily backups

## 🔧 Troubleshooting

### Bot Won't Start
```bash
# Check API service
sudo systemctl status nft-api

# Check logs
sudo journalctl -u nft-api -n 50

# Test AWS credentials
python3.11 -c "import boto3; print(boto3.client('sts').get_caller_identity())"
```

### Transaction Failures
1. Check wallet balances in dashboard
2. Verify contract addresses are correct
3. Check RPC endpoints are responding
4. Review transaction logs in CSV

### Email Not Sending
```bash
# Verify SES email
aws ses get-identity-verification-attributes --identities your-email@example.com

# Check SES sending limits
aws ses get-send-quota
```

### Low Gas Alerts
1. Fund owner wallet with AVAX
2. Bot will automatically resume when balance is sufficient

## 💰 Cost Estimate

**Monthly AWS Costs:**
- EC2 t3.small: ~$15/month
- S3 storage (1GB): ~$0.02/month
- SNS (1000 notifications): ~$0.50/month
- SES (1000 emails): ~$0.10/month
- Data transfer: ~$1/month

**Total: ~$17/month**

## 📝 Manual Commands

### Start/Stop via SSH
```bash
# Start bot manually
cd ~/nft-bot
python3.11 bot.py &

# Stop bot
pkill -f bot.py

# Restart API
sudo systemctl restart nft-api
```

### Export CSV Manually
```bash
# Copy to local machine
scp -i your-key.pem ec2-user@your-ec2-ip:~/nft-bot/nft_minting_records.csv ./
```

### Check Wallet Balances
```bash
cd ~/nft-bot
python3.11 << EOF
from web3 import Web3
from eth_account import Account
import boto3, json

# Get key
sm = boto3.client('secretsmanager')
secret = json.loads(sm.get_secret_value(SecretId='nft-bot-owner-key')['SecretString'])
address = Account.from_key(secret['private_key']).address

# Check balances
w3_test = Web3(Web3.HTTPProvider('https://api.avax-test.network/ext/bc/C/rpc'))
w3_main = Web3(Web3.HTTPProvider('https://api.avax.network/ext/bc/C/rpc'))

print(f"Address: {address}")
print(f"Testnet: {w3_test.from_wei(w3_test.eth.get_balance(address), 'ether')} AVAX")
print(f"Mainnet: {w3_main.from_wei(w3_main.eth.get_balance(address), 'ether')} AVAX")
EOF
```

## 🎉 You're All Set!

Your NFT minting bot is now fully deployed and ready to mint!

Access your dashboard at: `http://your-ec2-ip`

For support or issues, check the logs and AWS CloudWatch.
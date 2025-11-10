# NFT Minting Bot - Avalanche Network

Automated NFT minting bot for Early Puppeteer NFTs on Avalanche Mainnet and Testnet.

## Features

- **Automated Minting**: Mints NFTs to generated wallets automatically
- **True Randomness**: Uses cryptographically secure randomness (not Math.random)
- **Smart Network Switching**: Randomly switches between testnet/mainnet (3/5/7 cycle)
- **Human-like Behavior**: 20 different random sleep patterns (1-30 minutes)
- **Daily Limits**: 4000-6300 mainnet transactions per day (randomized)
- **Gas Sponsorship**: Owner wallet pays gas, recipients receive NFTs
- **AWS Integration**: Secure key storage, backups, alerts, and email
- **Real-time Dashboard**: Monitor bot status, transactions, and balances
- **Automatic Backups**: Daily S3 backups and email exports
- **Smart Alerts**: SNS/Email notifications for failures, low gas, start/stop

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    NFT MINTING BOT                         │
├───────────────────────────────────────────────────────────┤
│  ┌──────────────┐         ┌──────────────┐               │
│  │   bot.py     │◀───────▶│   api.py     │               │
│  │  (Minting)   │         │  (REST API)  │               │
│  └──────┬───────┘         └──────┬───────┘               │
│         │                        │                        │
│  ┌──────▼────────────────────────▼───────┐               │
│  │        index.html (Dashboard)         │               │
│  └───────────────────────────────────────┘               │
└───────────────────────────────────────────────────────────┘
        │             │             │
┌───────▼──────┐ ┌───▼────┐ ┌─────▼─────┐
│ AWS Secrets  │ │ AWS S3 │ │  AWS SNS  │
│   Manager    │ │Backups │ │  Alerts   │
└──────────────┘ └────────┘ └───────────┘
        │             │
        └─────────────┼─────────────┐
                      │             │
              ┌───────▼──────┐ ┌───▼────┐
              │  Avalanche   │ │AWS SES │
              │   Mainnet   │ │ Email  │
              │   Testnet   │ └────────┘
              └──────────────┘
```

## Prerequisites

- AWS Account with IAM permissions
- EC2 instance (t3.small or larger) with Amazon Linux 2023 or Ubuntu 22.04
- Owner wallet with AVAX on both testnet and mainnet
- Email verified in AWS SES

## File Structure

```
nft-bot/
├── bot.py                    # Main minting bot
├── api.py                    # Flask API server
├── requirements.txt          # Python dependencies
├── index.html               # Dashboard UI
├── deploy.sh                # Deployment script
├── nft_minting_records.csv  # Transaction records (created at runtime)
├── bot.log                  # Bot logs (created at runtime)
└── bot.pid                  # Process ID file (created at runtime)
```

## Deployment Guide

### Step 1: AWS Setup

#### 1.1 Create IAM Role for EC2

1. Go to IAM → Roles → Create Role
2. Select "EC2" as trusted entity
3. Attach these policies:
   - AmazonS3FullAccess
   - AmazonSNSFullAccess
   - AmazonSESFullAccess
   - SecretsManagerReadWrite
4. Name it: `nft-bot-ec2-role`
5. Note the role ARN

#### 1.2 Create S3 Bucket

```bash
aws s3 mb s3://nft-minting-bot-data --region us-east-1
```

#### 1.3 Create SNS Topic

```bash
aws sns create-topic --name nft-bot-alerts --region us-east-1
# Note the Topic ARN from output
```

#### 1.4 Subscribe Email to SNS

```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:nft-bot-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
# Confirm subscription via email
```

#### 1.5 Verify Email in SES

```bash
aws ses verify-email-identity --email-address your-email@example.com --region us-east-1
# Check email and click verification link
```

#### 1.6 Store Private Key in Secrets Manager

```bash
aws secretsmanager create-secret \
  --name nft-bot-owner-key \
  --description "Owner wallet private key" \
  --secret-string '{"private_key":"0xYOUR_PRIVATE_KEY_HERE"}' \
  --region us-east-1
```

### Step 2: Launch EC2 Instance

1. Launch EC2 instance:
   - Instance Type: t3.small or larger
   - OS: Amazon Linux 2023 or Ubuntu 22.04
   - Storage: 20GB+ SSD
   - Security Group: Allow ports 22 (SSH), 80 (HTTP), 443 (HTTPS optional)
   - IAM Role: Attach `nft-bot-ec2-role` created in Step 1.1

2. Note your EC2 public IP address

### Step 3: Upload Files to EC2

From your local machine:

```bash
scp -i your-key.pem \
    bot.py \
    api.py \
    index.html \
    requirements.txt \
    deploy.sh \
    ec2-user@YOUR_EC2_IP:~/
```

### Step 4: Deploy on EC2

SSH into your EC2 instance:

```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_IP
```

Create project directory and move files:

```bash
mkdir -p ~/nft-bot
cd ~/nft-bot
mv ~/*.py ~/*.html ~/*.txt ~/*.sh . 2>/dev/null || true
```

Run deployment script:

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Validate required files
2. Ask for configuration (AWS Region, SNS Topic ARN, Email, S3 Bucket, Secret Name)
3. Install system dependencies (Python 3.11, Nginx, Git)
4. Install Python packages
5. Configure environment variables
6. Create systemd service for API
7. Configure Nginx
8. Setup firewall
9. Test AWS connectivity
10. Start API service

**When prompted, provide:**
- AWS Region: `us-east-1` (or your region)
- SNS Topic ARN: From Step 1.3
- Email: Your verified email
- S3 Bucket: `nft-minting-bot-data` (or your bucket name)
- Secret Name: `nft-bot-owner-key` (or your secret name)

### Step 5: Verify Deployment

Check services:

```bash
# Check API service
sudo systemctl status nft-api

# Check Nginx
sudo systemctl status nginx

# Test API endpoint
curl http://localhost:5000/health
```

Access dashboard: `http://YOUR_EC2_IP`

You should see:
- Bot status (Stopped initially)
- Statistics (all zeros)
- Wallet balances
- Start/Stop buttons

### Step 6: Start Bot

1. Open dashboard: `http://YOUR_EC2_IP`
2. Click **"Start Bot"** button
3. Bot will start minting automatically
4. Monitor via dashboard

## Usage

### Starting the Bot

1. Open dashboard at `http://YOUR_EC2_IP`
2. Click "Start Bot"
3. Monitor logs and transactions in real-time

### Stopping the Bot

1. Click "Stop Bot" in dashboard
2. Bot will finish current transaction and stop
3. Final report will be emailed

### Exporting Data

- **Download CSV**: Click "Download CSV" button in dashboard
- **Email CSV**: Click "Email CSV" button in dashboard

## Bot Behavior

### Minting Flow

1. Generate new recipient wallet
   - Save address & private key to CSV
2. Random sleep (1-30 minutes)
   - 20 different patterns
   - Mix of odd/even durations
3. Determine network
   - Random cycle: 3, 5, or 7 testnet = 1 mainnet
4. Mint NFT
   - Owner pays gas
   - Recipient receives NFT
5. Record transaction
   - Save to CSV
   - Backup to S3 (every 100 mints)
6. Repeat

### Daily Limits

- Mainnet: 4,000 - 6,300 transactions/day (random)
- Testnet: Unlimited
- Resets at midnight UTC

### Gas Management

- Checks balance before each mint
- Alerts when below 0.5 AVAX
- Auto-stops if insufficient gas
- Resumes automatically when funded

## API Endpoints

### Bot Control

```bash
# Start bot
POST /api/bot/start

# Stop bot
POST /api/bot/stop

# Get status
GET /api/bot/status
```

### Data & Stats

```bash
# Get statistics
GET /api/stats

# Get transactions
GET /api/transactions?limit=50

# Get logs
GET /api/logs?lines=100
```

### Export

```bash
# Download CSV
GET /api/export/csv

# Email CSV
POST /api/export/email
Body: {"email": "recipient@example.com"}
```

### AWS Info

```bash
# Get wallet balances
GET /api/aws/balance

# List S3 backups
GET /api/aws/s3/backups
```

## Alerts & Notifications

### Start/Stop Alerts
- Subject: 🚀 Bot Started / 🛑 Bot Stopped
- Body: Bot info, balances, timestamp

### Low Gas Alerts
- Subject: 🚨 LOW GAS ALERT
- Body: Current balance, network
- Action: Bot stops until funded

### Failed Transaction Alerts
- Subject: ⚠️ Transaction Failed
- Body: Network, explorer URL, error

### Daily Reports
- Subject: 📊 Daily Report
- Body: Total minted, today's count
- Attachment: CSV file

## Security

### Private Key Storage
- Owner private key stored in **AWS Secrets Manager**
- Never exposed in code or logs
- Retrieved only when needed

### Generated Wallet Keys
- Stored in CSV with corresponding addresses
- Backed up to S3 daily
- Recipients have full control of their wallets

### Access Control
- Dashboard protected by AWS Security Groups
- API only accessible via Nginx proxy
- SSH access restricted to specific IPs

## Maintenance

### View Logs

```bash
# API logs
sudo journalctl -u nft-api -f

# Bot logs
tail -f ~/nft-bot/bot.log

# Nginx logs
sudo tail -f /var/log/nginx/access.log
```

### Restart Services

```bash
# Restart API
sudo systemctl restart nft-api

# Restart Nginx
sudo systemctl restart nginx
```

### Manual Backup

```bash
cd ~/nft-bot

# Backup to S3
aws s3 cp nft_minting_records.csv s3://nft-minting-bot-data/manual_backup_$(date +%Y%m%d).csv

# Download locally
scp -i your-key.pem ec2-user@YOUR_EC2_IP:~/nft-bot/nft_minting_records.csv ./
```

### Update Bot

```bash
cd ~/nft-bot

# Upload new files (using scp)
# Restart services
sudo systemctl restart nft-api

# If bot is running, stop and start via dashboard
```

## Testing

### Test AWS Connectivity

```bash
cd ~/nft-bot

# Test credentials
python3.11 -c "import boto3; print(boto3.client('sts').get_caller_identity())"

# Test Secrets Manager
python3.11 -c "import boto3; print(boto3.client('secretsmanager').get_secret_value(SecretId='nft-bot-owner-key'))"

# Test S3
aws s3 ls s3://nft-minting-bot-data
```

### Test Web3 Connection

```bash
python3.11 << EOF
from web3 import Web3

w3_test = Web3(Web3.HTTPProvider('https://api.avax-test.network/ext/bc/C/rpc'))
w3_main = Web3(Web3.HTTPProvider('https://api.avax.network/ext/bc/C/rpc'))

print(f"Testnet: {'Connected' if w3_test.is_connected() else 'Failed'}")
print(f"Mainnet: {'Connected' if w3_main.is_connected() else 'Failed'}")
EOF
```

## Troubleshooting

### Bot Won't Start

```bash
# Check API status
sudo systemctl status nft-api

# Check logs
sudo journalctl -u nft-api -n 50

# Check AWS credentials
aws sts get-caller-identity

# Check secret access
aws secretsmanager get-secret-value --secret-id nft-bot-owner-key
```

### Dashboard Not Loading

```bash
# Check Nginx
sudo systemctl status nginx
sudo nginx -t

# Check API
curl http://localhost:5000/health

# Check logs
sudo journalctl -u nft-api -n 50
```

### Transactions Failing

1. Check owner balance in dashboard
2. Verify contract addresses are correct
3. Test RPC connection
4. Review transaction logs in CSV

### Email Not Sending

```bash
# Verify SES email
aws ses get-identity-verification-attributes --identities your-email@example.com

# Check SES sending limits
aws ses get-send-quota
```

## Important Notes

1. **Owner Wallet Funding**
   - Keep sufficient AVAX balance (recommend 5+ AVAX on testnet, 100+ AVAX on mainnet)
   - Bot stops automatically when low on gas
   - Set up balance monitoring alerts

2. **Contract Addresses**
   - Testnet: `0x29c3fbb7f41F5fdaBD7cDBB3673f822D94B8D9C6`
   - Mainnet: `0xcFac9ca961EfB1b4038fe0963592e62BA8D5Ccb7`

3. **CSV Security**
   - Contains recipient private keys
   - Backed up to private S3 bucket
   - Download and store securely offline

4. **Rate Limiting**
   - Avalanche RPC: ~100 req/sec
   - Bot designed to stay well below limits
   - Random sleep patterns prevent detection

## Cost Breakdown

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| EC2 t3.small | 24/7 | ~$15 |
| S3 Storage | 1-10 GB | ~$0.23 |
| SNS Notifications | ~1000/month | ~$0.50 |
| SES Emails | ~100/month | ~$0.01 |
| Data Transfer | ~10 GB | ~$0.90 |
| **Total** | | **~$17/month** |

## Quick Reference

**Dashboard URL:** `http://YOUR_EC2_IP`  
**API Health:** `http://YOUR_EC2_IP/api/health`  
**Project Directory:** `~/nft-bot`  
**Logs:** `~/nft-bot/bot.log`  
**CSV Records:** `~/nft-bot/nft_minting_records.csv`

**Useful Commands:**
```bash
# View API logs
sudo journalctl -u nft-api -f

# View bot logs
tail -f ~/nft-bot/bot.log

# Restart API
sudo systemctl restart nft-api

# Stop bot via API
curl -X POST http://localhost:5000/api/bot/stop
```

## License

MIT License - Feel free to modify and use


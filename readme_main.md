# 🎨 NFT Minting Bot - Avalanche Network

Automated NFT minting bot for Early Puppeteer NFTs on Avalanche Mainnet and Testnet.

## ✨ Features

- ✅ **Automated Minting**: Mints NFTs to generated wallets automatically
- ✅ **True Randomness**: Uses cryptographically secure randomness (not Math.random)
- ✅ **Smart Network Switching**: Randomly switches between testnet/mainnet (3/5/7 cycle)
- ✅ **Human-like Behavior**: 20 different random sleep patterns (1-30 minutes)
- ✅ **Daily Limits**: 4000-6300 mainnet transactions per day (randomized)
- ✅ **Gas Sponsorship**: Owner wallet pays gas, recipients receive NFTs
- ✅ **AWS Integration**: Secure key storage, backups, alerts, and email
- ✅ **Real-time Dashboard**: Monitor bot status, transactions, and balances
- ✅ **Automatic Backups**: Daily S3 backups and email exports
- ✅ **Smart Alerts**: SNS/Email notifications for failures, low gas, start/stop

## 🏗️ Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    NFT MINTING BOT                         │
├───────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────┐         ┌──────────────┐               │
│  │   bot.py     │◀───────▶│   api.py     │               │
│  │  (Minting)   │         │  (REST API)  │               │
│  └──────┬───────┘         └──────┬───────┘               │
│         │                        │                        │
│         │                        │                        │
│  ┌──────▼────────────────────────▼───────┐               │
│  │        index.html (Dashboard)         │               │
│  │  - Start/Stop Bot                     │               │
│  │  - View Stats & Transactions          │               │
│  │  - Export CSV & Email                 │               │
│  └───────────────────────────────────────┘               │
└───────────────────────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
┌───────▼──────┐ ┌───▼────┐ ┌─────▼─────┐
│ AWS Secrets  │ │ AWS S3 │ │  AWS SNS  │
│   Manager    │ │Backups │ │  Alerts   │
│(Private Key) │ └────────┘ └───────────┘
└──────────────┘      │
        │             │
        └─────────────┼─────────────┐
                      │             │
              ┌───────▼──────┐ ┌───▼────┐
              │  Avalanche   │ │AWS SES │
              │   Mainnet    │ │ Email  │
              │   Testnet    │ └────────┘
              └──────────────┘
```

## 📋 Prerequisites

- AWS Account with IAM permissions
- EC2 instance (t3.small or larger)
- Owner wallet with AVAX on both networks
- Email verified in AWS SES

## 🚀 Quick Start (5 Minutes)

### 1. Setup AWS Resources

```bash
# Create S3 bucket
aws s3 mb s3://nft-minting-bot-data

# Create SNS topic
aws sns create-topic --name nft-bot-alerts

# Subscribe email
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:nft-bot-alerts \
  --protocol email \
  --notification-endpoint your@email.com

# Store private key in Secrets Manager
aws secretsmanager create-secret \
  --name nft-bot-owner-key \
  --secret-string '{"private_key":"0xYOUR_PRIVATE_KEY"}'

# Verify email in SES
aws ses verify-email-identity --email-address your@email.com
```

### 2. Launch EC2 & Deploy

```bash
# SSH into your EC2 instance
ssh -i your-key.pem ec2-user@your-ec2-ip

# Upload all files to ~/nft-bot/

# Run deployment script
cd ~/nft-bot
chmod +x deploy.sh
./deploy.sh
```

The script will:
- ✅ Install all dependencies
- ✅ Configure environment
- ✅ Setup systemd services
- ✅ Configure Nginx
- ✅ Start API server

### 3. Access Dashboard

Open: `http://your-ec2-ip`

Click **"Start Bot"** to begin minting!

## 📊 Dashboard Features

### Real-time Statistics
- Total minted NFTs
- Mainnet vs Testnet count
- Success vs Failed transactions
- Today's minting count

### Wallet Information
- Owner address
- Testnet AVAX balance
- Mainnet AVAX balance

### Transaction History
- Recent 20 transactions
- Network, recipient, status
- Direct links to Snowtrace explorer

### Bot Logs
- Live log streaming
- Last 50 log entries
- Auto-refresh every 10 seconds

### Export Options
- **Download CSV**: Get complete records
- **Email CSV**: Send to configured email

## 🔐 Security

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

## 📈 Bot Behavior

### Minting Flow
```
1. Generate new recipient wallet
   ├─ Save address & private key to CSV
   │
2. Random sleep (1-30 minutes)
   ├─ 20 different patterns
   ├─ Mix of odd/even durations
   │
3. Determine network
   ├─ Random cycle: 3, 5, or 7 testnet = 1 mainnet
   │
4. Mint NFT
   ├─ Owner pays gas
   ├─ Recipient receives NFT
   │
5. Record transaction
   ├─ Save to CSV
   ├─ Backup to S3 (every 100 mints)
   │
6. Repeat
```

### Daily Limits
- Mainnet: 4,000 - 6,300 transactions/day (random)
- Testnet: Unlimited
- Resets at midnight UTC

### Gas Management
- Checks balance before each mint
- Alerts when below 0.5 AVAX
- Auto-stops if insufficient gas
- Resumes automatically when funded

## 🛠️ API Endpoints

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

## 📧 Alerts & Notifications

### Start/Stop Alerts
```
Subject: 🚀 Bot Started
Body: Bot info, balances, timestamp
```

### Low Gas Alerts
```
Subject: 🚨 LOW GAS ALERT
Body: Current balance, network
Action: Bot stops until funded
```

### Failed Transaction Alerts
```
Subject: ⚠️ Transaction Failed
Body: Network, explorer URL, error
```

### Daily Reports
```
Subject: 📊 Daily Report
Body: Total minted, today's count
Attachment: CSV file
```

## 📁 File Structure

```
nft-bot/
├── bot.py                    # Main minting bot
├── api.py                    # Flask API server
├── requirements.txt          # Python dependencies
├── index.html               # Dashboard UI
├── deploy.sh                # Deployment script
├── nft_minting_records.csv  # Transaction records
├── bot.log                  # Bot logs
└── bot.pid                  # Process ID file
```

## 🧪 Testing

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

### Manual Mint Test
```bash
# Test single mint on testnet
python3.11 << EOF
from bot import *
owner_key = get_owner_private_key()
w3_t, w3_m, owner_acc, owner_addr, test_contract, main_contract = setup_web3(owner_key)
wallet = generate_new_wallet()
print(f"Test wallet: {wallet['address']}")
tx, status, gas = mint_nft('testnet', wallet['address'], owner_acc, owner_addr, w3_t, w3_m, test_contract, main_contract, owner_key)
print(f"Status: {status}")
print(f"TX: {tx}")
EOF
```

## 🔧 Maintenance

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
scp -i your-key.pem ec2-user@your-ec2-ip:~/nft-bot/nft_minting_records.csv ./
```

### Update Bot
```bash
cd ~/nft-bot

# Pull latest code
# (upload new files)

# Restart services
sudo systemctl restart nft-api

# If bot is running, stop and start via dashboard
```

## 💰 Cost Breakdown

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| EC2 t3.small | 24/7 | ~$15 |
| S3 Storage | 1-10 GB | ~$0.23 |
| SNS Notifications | ~1000/month | ~$0.50 |
| SES Emails | ~100/month | ~$0.01 |
| Data Transfer | ~10 GB | ~$0.90 |
| **Total** | | **~$17/month** |

## ⚠️ Important Notes

1. **Owner Wallet Funding**
   - Keep sufficient AVAX balance
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

## 🐛 Troubleshooting

### Bot Won't Start
```bash
# Check API status
sudo systemctl status nft-api

# Check AWS credentials
aws sts get-caller-identity

# Check secret access
aws secretsmanager get-secret-value --secret-id nft-bot-owner-key
```

### Transactions Failing
1. Check owner balance in dashboard
2. Verify contract addresses
3. Test RPC connection
4. Check transaction logs in CSV

### Dashboard Not Loading
```bash
# Check Nginx
sudo systemctl status nginx

# Check API
curl http://localhost:5000/health

# Check logs
sudo journalctl -u nft-api -n 50
```

## 📞 Support

For issues or questions:
1. Check logs: `sudo journalctl -u nft-api -f`
2. Review CSV for transaction history
3. Check AWS CloudWatch for detailed logs
4. Verify Security Group rules

## 📄 License

MIT License - Feel free to modify and use

## 🎉 Ready to Deploy?

Follow the deployment guide and start minting in minutes!

```bash
./deploy.sh
```

Access dashboard → Click "Start Bot" → Watch the magic happen! ✨
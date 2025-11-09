# 📋 Pre-Deployment Checklist

## ✅ AWS Account Setup

### 1. IAM User/Role
- [ ] Created IAM user with programmatic access
- [ ] Attached required policies:
  - [ ] AmazonS3FullAccess (or custom S3 policy)
  - [ ] AmazonSNSFullAccess
  - [ ] AmazonSESFullAccess
  - [ ] SecretsManagerReadWrite
  - [ ] AmazonEC2FullAccess
- [ ] Downloaded access key and secret key
- [ ] Configured AWS CLI: `aws configure`

### 2. S3 Bucket
- [ ] Created S3 bucket: `nft-minting-bot-data`
- [ ] Set bucket region: `us-east-1` (or your preferred)
- [ ] Enabled versioning (optional but recommended)
- [ ] Configured lifecycle rules for old backups (optional)

```bash
aws s3 mb s3://nft-minting-bot-data --region us-east-1
aws s3api put-bucket-versioning \
  --bucket nft-minting-bot-data \
  --versioning-configuration Status=Enabled
```

### 3. SNS Topic
- [ ] Created SNS topic: `nft-bot-alerts`
- [ ] Noted Topic ARN: `arn:aws:sns:us-east-1:XXXX:nft-bot-alerts`
- [ ] Created email subscription
- [ ] Confirmed subscription via email
- [ ] Tested notification

```bash
aws sns create-topic --name nft-bot-alerts --region us-east-1
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:nft-bot-alerts \
  --protocol email \
  --notification-endpoint your-email@example.com
```

### 4. SES Email Setup
- [ ] Verified sender email address
- [ ] Checked verification status (must be "Verified")
- [ ] If production: Requested SES production access (takes 24-48 hours)
- [ ] Tested sending email

```bash
aws ses verify-email-identity --email-address your-email@example.com --region us-east-1
aws ses get-identity-verification-attributes \
  --identities your-email@example.com --region us-east-1
```

### 5. Secrets Manager
- [ ] Created secret: `nft-bot-owner-key`
- [ ] Stored owner wallet private key in format: `{"private_key":"0x..."}`
- [ ] Tested secret retrieval
- [ ] Noted Secret ARN

```bash
aws secretsmanager create-secret \
  --name nft-bot-owner-key \
  --description "Owner wallet private key for NFT bot" \
  --secret-string '{"private_key":"0xYOUR_PRIVATE_KEY_HERE"}' \
  --region us-east-1
```

### 6. EC2 Instance
- [ ] Launched EC2 instance (t3.small or larger)
- [ ] Selected Amazon Linux 2023 or Ubuntu 22.04
- [ ] Configured storage: 20GB+ SSD
- [ ] Created/selected key pair for SSH
- [ ] Configured Security Group:
  - [ ] Port 22 (SSH) - Your IP only
  - [ ] Port 80 (HTTP) - Anywhere (0.0.0.0/0)
  - [ ] Port 443 (HTTPS) - Anywhere (optional)
- [ ] Assigned Elastic IP (optional but recommended)
- [ ] Created IAM role with required policies
- [ ] Attached IAM role to EC2 instance

## ✅ Wallet Setup

### Owner Wallet
- [ ] Have owner wallet private key
- [ ] Owner wallet has sufficient AVAX on Testnet (recommend 5+ AVAX)
- [ ] Owner wallet has sufficient AVAX on Mainnet (recommend 100+ AVAX)
- [ ] Owner wallet is set as contract owner (already done based on your contracts)
- [ ] Tested calling `mint` function manually on both networks

### Contract Verification
- [ ] Testnet contract verified: `0x29c3fbb7f41F5fdaBD7cDBB3673f822D94B8D9C6`
- [ ] Mainnet contract verified: `0xcFac9ca961EfB1b4038fe0963592e62BA8D5Ccb7`
- [ ] Both contracts initialized with owner address
- [ ] Set URI for both contracts (if not done yet)
- [ ] Both contracts NOT paused

## ✅ Network Configuration

### Avalanche RPCs
- [ ] Tested Testnet RPC: `https://api.avax-test.network/ext/bc/C/rpc`
- [ ] Tested Mainnet RPC: `https://api.avax.network/ext/bc/C/rpc`

```bash
# Test RPC connectivity
curl -X POST --data '{
  "jsonrpc":"2.0",
  "method":"eth_blockNumber",
  "params":[],
  "id":1
}' -H "Content-Type: application/json" https://api.avax-test.network/ext/bc/C/rpc
```

## ✅ Local Preparation

### Files Ready
- [ ] `bot.py` - Main minting bot
- [ ] `api.py` - Flask API server
- [ ] `requirements.txt` - Python dependencies
- [ ] `index.html` - Dashboard frontend
- [ ] `deploy.sh` - Deployment script
- [ ] `README.md` - Documentation

### Environment Variables Noted
- [ ] AWS_DEFAULT_REGION: `_____________`
- [ ] SNS_TOPIC_ARN: `_____________`
- [ ] EMAIL_RECIPIENT: `_____________`
- [ ] S3_BUCKET: `_____________`
- [ ] SECRET_NAME: `_____________`

## ✅ Domain & SSL (Optional)

### If Using Custom Domain
- [ ] Purchased domain
- [ ] Created A record pointing to EC2 Elastic IP
- [ ] DNS propagated (check with `nslookup your-domain.com`)
- [ ] Will install SSL certificate after deployment

## ✅ Pre-Deployment Tests

### AWS Connectivity
```bash
# Test from local machine
aws sts get-caller-identity
aws s3 ls s3://nft-minting-bot-data
aws sns list-topics
aws secretsmanager get-secret-value --secret-id nft-bot-owner-key
```

### Web3 Connection
```bash
# Test from local machine (requires web3.py installed)
python3 << EOF
from web3 import Web3
w3 = Web3(Web3.HTTPProvider('https://api.avax-test.network/ext/bc/C/rpc'))
print(f"Connected: {w3.is_connected()}")
print(f"Block: {w3.eth.block_number}")
EOF
```

## ✅ Deployment Checklist

### Upload Files to EC2
```bash
# From local machine
scp -i your-key.pem bot.py api.py requirements.txt index.html deploy.sh \
    ec2-user@YOUR_EC2_IP:~/
```

### Run Deployment
```bash
# SSH to EC2
ssh -i your-key.pem ec2-user@YOUR_EC2_IP

# Create directory
mkdir -p ~/nft-bot
cd ~/nft-bot

# Move files
mv ~/*.py ~/*.txt ~/*.html ~/*.sh .

# Make deploy script executable
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

## ✅ Post-Deployment Verification

### Services Running
```bash
# Check API service
sudo systemctl status nft-api

# Check Nginx
sudo systemctl status nginx

# Test API endpoint
curl http://localhost:5000/health
```

### Dashboard Access
- [ ] Dashboard loads at `http://YOUR_EC2_IP`
- [ ] Bot status shows "Stopped"
- [ ] Statistics show all zeros (normal for first run)
- [ ] Wallet balances display correctly
- [ ] Start/Stop buttons work

### Test Bot
- [ ] Click "Start Bot" button
- [ ] Bot status changes to "Running"
- [ ] Logs appear in dashboard
- [ ] First wallet generated
- [ ] First mint transaction successful
- [ ] Transaction appears in CSV
- [ ] Received start alert via email/SNS

### Monitoring
- [ ] Set up CloudWatch alarms for:
  - [ ] EC2 CPU > 80%
  - [ ] Disk space < 20%
  - [ ] Memory > 80%
- [ ] Add calendar reminder to check daily for first week
- [ ] Bookmark dashboard URL

## ✅ Emergency Contacts & Info

### Important URLs
- Dashboard: `http://YOUR_EC2_IP`
- Testnet Explorer: `https://testnet.snowtrace.io`
- Mainnet Explorer: `https://snowtrace.io`
- AWS Console: `https://console.aws.amazon.com`

### Important Commands
```bash
# Stop bot immediately
curl -X POST http://localhost:5000/api/bot/stop

# View logs
tail -f ~/nft-bot/bot.log

# Download CSV
scp -i your-key.pem ec2-user@YOUR_EC2_IP:~/nft-bot/nft_minting_records.csv ./

# Check balances
cd ~/nft-bot && python3.11 -c "
from bot import *
key = get_owner_private_key()
from eth_account import Account
addr = Account.from_key(key).address
from web3 import Web3
w3_t = Web3(Web3.HTTPProvider('https://api.avax-test.network/ext/bc/C/rpc'))
w3_m = Web3(Web3.HTTPProvider('https://api.avax.network/ext/bc/C/rpc'))
print(f'Testnet: {w3_t.from_wei(w3_t.eth.get_balance(addr), \"ether\")} AVAX')
print(f'Mainnet: {w3_m.from_wei(w3_m.eth.get_balance(addr), \"ether\")} AVAX')
"
```

## ✅ Backup Plan

### Regular Backups
- [ ] CSV auto-backed to S3 daily ✅ (automatic)
- [ ] Email CSV to yourself weekly (manual via dashboard)
- [ ] Download CSV locally monthly
- [ ] Test restore procedure

### Disaster Recovery
- [ ] Documented process to restore from S3 backup
- [ ] Tested launching new EC2 and restoring service
- [ ] Have backup of deployment script and configs

## 🎉 Ready to Deploy!

Once all checkboxes are complete, you're ready to deploy!

### Quick Deploy Command
```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_IP
cd ~/nft-bot
./deploy.sh
```

### Post-Deploy
1. Open `http://YOUR_EC2_IP` in browser
2. Click **"Start Bot"**
3. Watch the magic happen! ✨

## 📊 Monitoring Schedule

### Daily (First Week)
- Check dashboard stats
- Verify transactions in Snowtrace
- Review logs for errors
- Check wallet balances

### Weekly (After First Week)
- Review CSV export
- Check S3 backup status
- Verify no failed transactions
- Monitor AWS costs

### Monthly
- Download CSV locally
- Review total minted count
- Check if pace is meeting goals
- Optimize if needed

---

**Questions or Issues?**
- Check logs: `sudo journalctl -u nft-api -f`
- Review deployment guide
- Test AWS connectivity
- Verify Security Group rules
# bot.py - Main NFT Minting Bot
import os
import csv
import time
import secrets
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from web3 import Web3
from eth_account import Account
import boto3
from decimal import Decimal
from botocore.exceptions import ClientError

# ============================================
# LOGGING SETUP
# ============================================
def setup_logging():
    """Setup logging with rotation - clears on restart"""
    # Remove existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler - overwrite on restart (mode='w')
    file_handler = logging.FileHandler('bot.log', mode='w')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

# ============================================
# AWS CLIENTS
# ============================================
sns_client = boto3.client('sns')
ses_client = boto3.client('ses')
secretsmanager_client = boto3.client('secretsmanager')
s3_client = boto3.client('s3')

# ============================================
# CONFIGURATION FROM ENVIRONMENT
# ============================================
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')
EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT')
S3_BUCKET = os.getenv('S3_BUCKET', 'nft-minting-bot-data')
SECRET_NAME = os.getenv('SECRET_NAME', 'nft-bot-owner-key')

TESTNET_CONTRACT = '0x29c3fbb7f41F5fdaBD7cDBB3673f822D94B8D9C6'
MAINNET_CONTRACT = '0xcFac9ca961EfB1b4038fe0963592e62BA8D5Ccb7'
TOKEN_ID = 1
AMOUNT = 1

# Avalanche RPC endpoints
TESTNET_RPC = 'https://api.avax-test.network/ext/bc/C/rpc'
MAINNET_RPC = 'https://api.avax.network/ext/bc/C/rpc'

# Gas thresholds
MIN_GAS_THRESHOLD = Decimal('0.01')

# Daily limits
MIN_MAINNET_TXNS_PER_DAY = 4000
MAX_MAINNET_TXNS_PER_DAY = 6300

# CSV file
CSV_FILE = 'nft_minting_records.csv'

# Contract ABI
CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"},
            {"internalType": "uint256", "name": "id", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "bytes", "name": "data", "type": "bytes"}
        ],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

# Sleep patterns (1-30 in seconds)
SLEEP_PATTERNS = [
    15, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 13, 14, 28
]

CYCLE_OPTIONS = [ 1, 2]

# ============================================
# TRUE RANDOMNESS
# ============================================
def true_random_choice(choices):
    return choices[secrets.randbelow(len(choices))]

def true_random_int(min_val, max_val):
    return secrets.randbelow(max_val - min_val + 1) + min_val

# ============================================
# AWS SECRETS MANAGER
# ============================================
def get_owner_private_key():
    """Retrieve owner private key from AWS Secrets Manager"""
    try:
        logger.info("Retrieving private key from Secrets Manager: %s", SECRET_NAME)
        response = secretsmanager_client.get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(response['SecretString'])
        logger.info("✅ Private key retrieved successfully")
        return secret['private_key']
    except ClientError as e:
        logger.error("❌ Error retrieving secret: %s", e)
        raise

# ============================================
# AWS SNS ALERTS
# ============================================
def send_alert(subject, message):
    """Send alert via AWS SNS"""
    try:
        logger.info("Sending SNS alert: %s", subject)
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        logger.info("✅ Alert sent successfully")
    except Exception as e:
        logger.error("❌ Failed to send alert: %s", e)

# ============================================
# AWS SES EMAIL WITH CSV ATTACHMENT
# ============================================
def send_email_with_csv():
    """Send email with CSV file as attachment"""
    try:
        logger.info("Preparing to email CSV file to %s", EMAIL_RECIPIENT)
        # Read CSV file
        with open(CSV_FILE, 'r') as f:
            csv_content = f.read()
        
        # Create MIME message
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication
        
        msg = MIMEMultipart()
        msg['Subject'] = f'NFT Minting Records - {datetime.now().strftime("%Y-%m-%d")}'
        msg['From'] = EMAIL_RECIPIENT
        msg['To'] = EMAIL_RECIPIENT
        
        # Body
        body = MIMEText(f"""
NFT Minting Bot - Daily Report

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Please find attached the complete minting records CSV file.

This is an automated email from your NFT Minting Bot.
        """)
        msg.attach(body)
        
        # Attachment
        attachment = MIMEApplication(csv_content)
        attachment.add_header('Content-Disposition', 'attachment', 
                            filename=f'nft_records_{datetime.now().strftime("%Y%m%d")}.csv')
        msg.attach(attachment)
        
        # Send
        ses_client.send_raw_email(
            Source=EMAIL_RECIPIENT,
            Destinations=[EMAIL_RECIPIENT],
            RawMessage={'Data': msg.as_string()}
        )
        logger.info("✅ CSV file emailed successfully")
        
    except Exception as e:
        logger.error("❌ Failed to send email: %s", e)
        send_alert("⚠️ Email Failed", f"Could not send CSV: {str(e)}")

# ============================================
# S3 BACKUP
# ============================================
def backup_to_s3():
    """Backup CSV file to S3"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_key = f"backups/nft_records_{timestamp}.csv"
        
        logger.info("Backing up CSV to S3: %s/%s", S3_BUCKET, s3_key)
        s3_client.upload_file(CSV_FILE, S3_BUCKET, s3_key)
        logger.info("✅ Backed up to S3 successfully")
    except Exception as e:
        logger.error("❌ S3 backup failed: %s", e)

# ============================================
# CSV MANAGEMENT
# ============================================
def init_csv():
    if not os.path.exists(CSV_FILE):
        logger.info("Initializing new CSV file: %s", CSV_FILE)
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'Network', 'Recipient_Address', 'Private_Key',
                'Transaction_Hash', 'Status', 'Explorer_URL', 'Gas_Used', 'Owner_Address'
            ])
        logger.info("✅ CSV file initialized")
    else:
        logger.info("CSV file already exists: %s", CSV_FILE)

def save_to_csv(network, recipient_addr, private_key, tx_hash, status, gas_used, owner_addr):
    timestamp = datetime.now().isoformat()
    
    explorer_url = f"https://{'testnet.' if network == 'testnet' else ''}snowtrace.io/tx/{tx_hash}" if tx_hash else 'N/A'
    
    logger.info("Saving transaction to CSV - Status: %s, Network: %s", status, network)
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp, network, recipient_addr, private_key,
            tx_hash if tx_hash else 'N/A', status, explorer_url, gas_used, owner_addr
        ])
    logger.info("✅ Transaction saved to CSV")

# ============================================
# WEB3 SETUP
# ============================================
def setup_web3(owner_private_key):
    logger.info("Setting up Web3 connections...")
    w3_testnet = Web3(Web3.HTTPProvider(TESTNET_RPC))
    w3_mainnet = Web3(Web3.HTTPProvider(MAINNET_RPC))
    
    logger.info("Testnet RPC: %s", TESTNET_RPC)
    logger.info("Mainnet RPC: %s", MAINNET_RPC)
    
    owner_account = Account.from_key(owner_private_key)
    owner_address = owner_account.address
    
    logger.info("Owner account loaded: %s", owner_address)
    
    testnet_contract = w3_testnet.eth.contract(
        address=Web3.to_checksum_address(TESTNET_CONTRACT),
        abi=CONTRACT_ABI
    )
    mainnet_contract = w3_mainnet.eth.contract(
        address=Web3.to_checksum_address(MAINNET_CONTRACT),
        abi=CONTRACT_ABI
    )
    
    logger.info("✅ Web3 connections established")
    logger.info("Testnet connected: %s", w3_testnet.is_connected())
    logger.info("Mainnet connected: %s", w3_mainnet.is_connected())
    
    return w3_testnet, w3_mainnet, owner_account, owner_address, testnet_contract, mainnet_contract

# ============================================
# WALLET MANAGEMENT
# ============================================
def generate_new_wallet():
    logger.info("Generating new recipient wallet...")
    account = Account.create()
    wallet = {
        'address': account.address,
        'private_key': account.key.hex()
    }
    logger.info("✅ New wallet generated: %s", wallet['address'])
    return wallet

def check_gas_balance(w3, address):
    balance_wei = w3.eth.get_balance(address)
    balance_avax = Decimal(w3.from_wei(balance_wei, 'ether'))
    return balance_avax

# ============================================
# MINTING FUNCTIONS
# ============================================
def mint_nft(network, recipient_address, owner_account, owner_address, w3_testnet, w3_mainnet, 
             testnet_contract, mainnet_contract, owner_private_key):
    """Mint NFT - Owner wallet pays gas and mints to recipient"""
    
    if network == 'testnet':
        w3 = w3_testnet
        contract = testnet_contract
        network_name = 'Testnet'
    else:
        w3 = w3_mainnet
        contract = mainnet_contract
        network_name = 'Mainnet'
    
    try:
        logger.info("[%s] Starting mint transaction", network_name)
        logger.info("[%s] Recipient: %s", network_name, recipient_address)
        
        # Check owner's gas balance
        balance = check_gas_balance(w3, owner_address)
        logger.info("[%s] Owner balance: %s AVAX", network_name, balance)
        
        if balance < MIN_GAS_THRESHOLD:
            alert_msg = f"Low gas alert! Owner balance: {balance} AVAX on {network_name}"
            logger.warning("[%s] ⚠️ Low gas - Balance below threshold", network_name)
            send_alert("🚨 LOW GAS ALERT", alert_msg)
            return None, 'FAILED_LOW_GAS', 0
        
        # Build transaction - Owner mints to recipient
        nonce = w3.eth.get_transaction_count(owner_address)
        logger.info("[%s] Current nonce: %d", network_name, nonce)
        
        logger.info("[%s] Estimating gas...", network_name)
        gas_estimate = contract.functions.mint(
            Web3.to_checksum_address(recipient_address),
            TOKEN_ID,
            AMOUNT,
            b''
        ).estimate_gas({'from': owner_address})
        logger.info("[%s] Estimated gas: %d", network_name, gas_estimate)
        
        gas_price = w3.eth.gas_price
        logger.info("[%s] Gas price: %s GWEI", network_name, w3.from_wei(gas_price, 'gwei'))
        
        logger.info("[%s] Building transaction...", network_name)
        txn = contract.functions.mint(
            Web3.to_checksum_address(recipient_address),
            TOKEN_ID,
            AMOUNT,
            b''
        ).build_transaction({
            'from': owner_address,
            'gas': gas_estimate + 10000,
            'gasPrice': gas_price,
            'nonce': nonce,
            'chainId': w3.eth.chain_id
        })
        
        # Owner signs and sends transaction
        logger.info("[%s] Signing transaction...", network_name)
        signed_txn = w3.eth.account.sign_transaction(txn, owner_private_key)
        
        logger.info("[%s] Sending transaction...", network_name)
        # FIXED: Use rawTransaction instead of raw_transaction
        tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_hash_hex = tx_hash.hex()
        
        logger.info("[%s] ✅ Transaction sent: %s", network_name, tx_hash_hex)
        logger.info("[%s] Waiting for confirmation (timeout: 300s)...", network_name)
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        
        if receipt['status'] == 1:
            logger.info("[%s] ✅ Transaction confirmed - Gas used: %d", network_name, receipt['gasUsed'])
            return tx_hash_hex, 'SUCCESS', receipt['gasUsed']
        else:
            logger.error("[%s] ❌ Transaction failed - Receipt status: 0", network_name)
            explorer_url = f"https://{'testnet.' if network == 'testnet' else ''}snowtrace.io/tx/{tx_hash_hex}"
            send_alert("⚠️ Transaction Failed", f"Failed on {network_name}\n{explorer_url}")
            return tx_hash_hex, 'FAILED', receipt['gasUsed']
            
    except Exception as e:
        error_msg = str(e)
        logger.error("[%s] ❌ Minting error: %s", network_name, error_msg)
        
        if 'insufficient funds' in error_msg.lower():
            logger.error("[%s] Insufficient funds detected", network_name)
            send_alert("🚨 INSUFFICIENT FUNDS", f"Bot stopped on {network_name}: {error_msg}")
            return None, 'FAILED_NO_GAS', 0
        
        send_alert("⚠️ Minting Error", f"Error on {network_name}: {error_msg[:200]}")
        return None, f'FAILED', 0

# ============================================
# MAIN BOT LOGIC
# ============================================
def run_bot():
    logger.info("=" * 60)
    logger.info("NFT MINTING BOT STARTING...")
    logger.info("=" * 60)
    logger.info("Bot process PID: %d", os.getpid())
    logger.info("Log file: %s", os.path.abspath('bot.log'))
    
    # Get owner private key from AWS Secrets Manager
    logger.info("🔐 Retrieving owner private key from AWS Secrets Manager...")
    owner_private_key = get_owner_private_key()
    
    # Setup Web3
    w3_testnet, w3_mainnet, owner_account, owner_address, testnet_contract, mainnet_contract = setup_web3(owner_private_key)
    
    logger.info("👤 Owner Address: %s", owner_address)
    logger.info("📄 Testnet Contract: %s", TESTNET_CONTRACT)
    logger.info("📄 Mainnet Contract: %s", MAINNET_CONTRACT)
    
    # Check initial balances
    testnet_balance = check_gas_balance(w3_testnet, owner_address)
    mainnet_balance = check_gas_balance(w3_mainnet, owner_address)
    logger.info("💰 Testnet Balance: %s AVAX", testnet_balance)
    logger.info("💰 Mainnet Balance: %s AVAX", mainnet_balance)
    logger.info("=" * 60)
    
    # Send startup alert
    send_alert(
        "🚀 Bot Started",
        f"""NFT Minting Bot has started successfully!

Owner: {owner_address}
Testnet Balance: {testnet_balance} AVAX
Mainnet Balance: {mainnet_balance} AVAX
Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    )
    
    init_csv()
    
    testnet_counter = 0
    mainnet_counter_today = 0
    total_minted = 0
    current_date = datetime.now().date()
    
    current_cycle = true_random_choice(CYCLE_OPTIONS)
    daily_mainnet_target = true_random_int(MIN_MAINNET_TXNS_PER_DAY, MAX_MAINNET_TXNS_PER_DAY)
    
    logger.info("🎯 Current cycle: Every %d testnet = 1 mainnet", current_cycle)
    logger.info("🎯 Daily mainnet target: %d", daily_mainnet_target)
    logger.info("=" * 60)
    
    try:
        while True:
            # New day check
            if datetime.now().date() != current_date:
                logger.info("🌅 NEW DAY - Date changed to %s", datetime.now().date())
                # Backup and email previous day's data
                backup_to_s3()
                send_email_with_csv()
                
                current_date = datetime.now().date()
                mainnet_counter_today = 0
                daily_mainnet_target = true_random_int(MIN_MAINNET_TXNS_PER_DAY, MAX_MAINNET_TXNS_PER_DAY)
                logger.info("New daily mainnet target: %d", daily_mainnet_target)
                
                send_alert("📊 Daily Report", f"New day started. Target: {daily_mainnet_target} mainnet mints")
            
            # Daily limit check
            if mainnet_counter_today >= daily_mainnet_target:
                logger.info("✅ Daily limit reached (%d/%d) - Sleeping for 1 hour", mainnet_counter_today, daily_mainnet_target)
                time.sleep(3600)
                continue
            
            # Generate new recipient wallet
            logger.info("")
            logger.info("=" * 60)
            logger.info("[%s] Starting new mint cycle", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            wallet = generate_new_wallet()
            logger.info("📍 Recipient: %s", wallet['address'])
            
            # Determine network
            testnet_counter += 1
            
            if testnet_counter >= current_cycle:
                network = 'mainnet'
                testnet_counter = 0
                current_cycle = true_random_choice(CYCLE_OPTIONS)
                logger.info("🔄 Cycle completed - Switching to mainnet")
                logger.info("Next cycle: Every %d testnet = 1 mainnet", current_cycle)
            else:
                network = 'testnet'
            
            logger.info("🌐 Target Network: %s", network.upper())
            logger.info("👤 Owner (gas payer): %s", owner_address)
            
            # Random sleep
            sleep_duration = true_random_choice(SLEEP_PATTERNS)
            logger.info("💤 Sleeping for %dm %ds to simulate human behavior...", sleep_duration // 60, sleep_duration % 60)
            time.sleep(sleep_duration)
            
            # Mint NFT (Owner pays gas, recipient receives NFT)
            logger.info("🎨 Initiating mint on %s", network.upper())
            logger.info("   Owner mints → Recipient receives")
            
            tx_hash, status, gas_used = mint_nft(
                network, wallet['address'], owner_account, owner_address,
                w3_testnet, w3_mainnet, testnet_contract, mainnet_contract,
                owner_private_key
            )
            
            # Save to CSV
            save_to_csv(network, wallet['address'], wallet['private_key'], 
                       tx_hash, status, gas_used, owner_address)
            
            # Update counters
            if status == 'SUCCESS':
                total_minted += 1
                if network == 'mainnet':
                    mainnet_counter_today += 1
                logger.info("📊 Progress - Total: %d | Today's mainnet: %d/%d", total_minted, mainnet_counter_today, daily_mainnet_target)
            
            # Handle failures
            if status.startswith('FAILED'):
                if 'LOW_GAS' in status or 'NO_GAS' in status:
                    logger.error("🛑 STOPPING BOT - Insufficient gas")
                    break
            
            # Periodic backup (every 100 mints)
            if total_minted % 100 == 0 and total_minted > 0:
                logger.info("📦 Periodic backup triggered (every 100 mints)")
                backup_to_s3()
                
    except KeyboardInterrupt:
        logger.info("")
        logger.info("👋 Bot stopped by user (KeyboardInterrupt)")
    except Exception as e:
        logger.error("❌ Critical error occurred: %s", str(e), exc_info=True)
        send_alert("🚨 Bot Crashed", f"Critical error: {str(e)}")
    finally:
        logger.info("")
        logger.info("=" * 60)
        logger.info("BOT SHUTDOWN SEQUENCE")
        logger.info("=" * 60)
        
        # Final backup and email
        logger.info("Performing final backup...")
        backup_to_s3()
        send_email_with_csv()
        
        # Send shutdown alert
        send_alert(
            "🛑 Bot Stopped",
            f"""NFT Minting Bot has stopped.

Total Minted: {total_minted}
Today's Mainnet: {mainnet_counter_today}
Stop Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

CSV file has been emailed and backed up to S3.
"""
        )
        
        logger.info("=" * 60)
        logger.info("BOT STOPPED")
        logger.info("Total minted: %d", total_minted)
        logger.info("Session duration: %s", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        logger.info("=" * 60)

if __name__ == "__main__":
    run_bot()

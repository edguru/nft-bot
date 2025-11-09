# bot.py - Main NFT Minting Bot
import os
import csv
import time
import secrets
import json
from datetime import datetime, timedelta
from web3 import Web3
from eth_account import Account
import boto3
from decimal import Decimal
from botocore.exceptions import ClientError

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
MIN_GAS_THRESHOLD = Decimal('0.5')

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

# Sleep patterns (1-30 minutes in seconds)
SLEEP_PATTERNS = [
    63, 127, 189, 243, 311, 367, 421, 487, 551, 613,
    677, 731, 797, 853, 911, 973, 1031, 1097, 1153, 1217,
    1283, 1337, 1409, 1471, 1531, 1597, 1661, 1723, 1787, 1800
]

CYCLE_OPTIONS = [3, 5, 7]

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
        response = secretsmanager_client.get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(response['SecretString'])
        return secret['private_key']
    except ClientError as e:
        print(f"Error retrieving secret: {e}")
        raise

# ============================================
# AWS SNS ALERTS
# ============================================
def send_alert(subject, message):
    """Send alert via AWS SNS"""
    try:
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"✉️ Alert sent: {subject}")
    except Exception as e:
        print(f"Failed to send alert: {e}")

# ============================================
# AWS SES EMAIL WITH CSV ATTACHMENT
# ============================================
def send_email_with_csv():
    """Send email with CSV file as attachment"""
    try:
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
        print("📧 CSV file emailed successfully!")
        
    except Exception as e:
        print(f"Failed to send email: {e}")
        send_alert("⚠️ Email Failed", f"Could not send CSV: {str(e)}")

# ============================================
# S3 BACKUP
# ============================================
def backup_to_s3():
    """Backup CSV file to S3"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        s3_key = f"backups/nft_records_{timestamp}.csv"
        
        s3_client.upload_file(CSV_FILE, S3_BUCKET, s3_key)
        print(f"☁️ Backed up to S3: {s3_key}")
    except Exception as e:
        print(f"S3 backup failed: {e}")

# ============================================
# CSV MANAGEMENT
# ============================================
def init_csv():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'Timestamp', 'Network', 'Recipient_Address', 'Private_Key',
                'Transaction_Hash', 'Status', 'Explorer_URL', 'Gas_Used', 'Owner_Address'
            ])

def save_to_csv(network, recipient_addr, private_key, tx_hash, status, gas_used, owner_addr):
    timestamp = datetime.now().isoformat()
    
    explorer_url = f"https://{'testnet.' if network == 'testnet' else ''}snowtrace.io/tx/{tx_hash}" if tx_hash else 'N/A'
    
    with open(CSV_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            timestamp, network, recipient_addr, private_key,
            tx_hash if tx_hash else 'N/A', status, explorer_url, gas_used, owner_addr
        ])

# ============================================
# WEB3 SETUP
# ============================================
def setup_web3(owner_private_key):
    w3_testnet = Web3(Web3.HTTPProvider(TESTNET_RPC))
    w3_mainnet = Web3(Web3.HTTPProvider(MAINNET_RPC))
    
    owner_account = Account.from_key(owner_private_key)
    owner_address = owner_account.address
    
    testnet_contract = w3_testnet.eth.contract(
        address=Web3.to_checksum_address(TESTNET_CONTRACT),
        abi=CONTRACT_ABI
    )
    mainnet_contract = w3_mainnet.eth.contract(
        address=Web3.to_checksum_address(MAINNET_CONTRACT),
        abi=CONTRACT_ABI
    )
    
    return w3_testnet, w3_mainnet, owner_account, owner_address, testnet_contract, mainnet_contract

# ============================================
# WALLET MANAGEMENT
# ============================================
def generate_new_wallet():
    account = Account.create()
    return {
        'address': account.address,
        'private_key': account.key.hex()
    }

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
        # Check owner's gas balance
        balance = check_gas_balance(w3, owner_address)
        print(f"[{network_name}] Owner balance: {balance} AVAX")
        
        if balance < MIN_GAS_THRESHOLD:
            alert_msg = f"Low gas alert! Owner balance: {balance} AVAX on {network_name}"
            send_alert("🚨 LOW GAS ALERT", alert_msg)
            return None, 'FAILED_LOW_GAS', 0
        
        # Build transaction - Owner mints to recipient
        nonce = w3.eth.get_transaction_count(owner_address)
        
        gas_estimate = contract.functions.mint(
            Web3.to_checksum_address(recipient_address),
            TOKEN_ID,
            AMOUNT,
            b''
        ).estimate_gas({'from': owner_address})
        
        txn = contract.functions.mint(
            Web3.to_checksum_address(recipient_address),
            TOKEN_ID,
            AMOUNT,
            b''
        ).build_transaction({
            'from': owner_address,
            'gas': gas_estimate + 10000,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
            'chainId': w3.eth.chain_id
        })
        
        # Owner signs and sends transaction
        signed_txn = w3.eth.account.sign_transaction(txn, owner_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
        tx_hash_hex = tx_hash.hex()
        
        print(f"[{network_name}] Transaction sent: {tx_hash_hex}")
        print(f"[{network_name}] Owner minting to: {recipient_address}")
        print(f"[{network_name}] Waiting for confirmation...")
        
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
        
        if receipt['status'] == 1:
            print(f"[{network_name}] ✅ Mint successful!")
            return tx_hash_hex, 'SUCCESS', receipt['gasUsed']
        else:
            print(f"[{network_name}] ❌ Transaction failed")
            explorer_url = f"https://{'testnet.' if network == 'testnet' else ''}snowtrace.io/tx/{tx_hash_hex}"
            send_alert("⚠️ Transaction Failed", f"Failed on {network_name}\n{explorer_url}")
            return tx_hash_hex, 'FAILED', receipt['gasUsed']
            
    except Exception as e:
        error_msg = str(e)
        print(f"[{network_name}] ❌ Error: {error_msg}")
        
        if 'insufficient funds' in error_msg.lower():
            send_alert("🚨 INSUFFICIENT FUNDS", f"Bot stopped on {network_name}: {error_msg}")
            return None, 'FAILED_NO_GAS', 0
        
        send_alert("⚠️ Minting Error", f"Error on {network_name}: {error_msg[:200]}")
        return None, f'FAILED', 0

# ============================================
# MAIN BOT LOGIC
# ============================================
def run_bot():
    print("=" * 60)
    print("NFT MINTING BOT STARTING...")
    print("=" * 60)
    
    # Get owner private key from AWS Secrets Manager
    print("🔐 Retrieving owner private key from AWS Secrets Manager...")
    owner_private_key = get_owner_private_key()
    
    # Setup Web3
    w3_testnet, w3_mainnet, owner_account, owner_address, testnet_contract, mainnet_contract = setup_web3(owner_private_key)
    
    print(f"👤 Owner Address: {owner_address}")
    print(f"📄 Testnet Contract: {TESTNET_CONTRACT}")
    print(f"📄 Mainnet Contract: {MAINNET_CONTRACT}")
    
    # Check initial balances
    testnet_balance = check_gas_balance(w3_testnet, owner_address)
    mainnet_balance = check_gas_balance(w3_mainnet, owner_address)
    print(f"💰 Testnet Balance: {testnet_balance} AVAX")
    print(f"💰 Mainnet Balance: {mainnet_balance} AVAX")
    print("=" * 60)
    
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
    
    print(f"🎯 Current cycle: Every {current_cycle} testnet = 1 mainnet")
    print(f"🎯 Daily mainnet target: {daily_mainnet_target}")
    print("=" * 60)
    
    try:
        while True:
            # New day check
            if datetime.now().date() != current_date:
                # Backup and email previous day's data
                backup_to_s3()
                send_email_with_csv()
                
                current_date = datetime.now().date()
                mainnet_counter_today = 0
                daily_mainnet_target = true_random_int(MIN_MAINNET_TXNS_PER_DAY, MAX_MAINNET_TXNS_PER_DAY)
                print(f"\n🌅 NEW DAY - Target: {daily_mainnet_target} mainnet transactions")
                
                send_alert("📊 Daily Report", f"New day started. Target: {daily_mainnet_target} mainnet mints")
            
            # Daily limit check
            if mainnet_counter_today >= daily_mainnet_target:
                print(f"\n✅ Daily limit reached ({mainnet_counter_today}/{daily_mainnet_target})")
                time.sleep(3600)
                continue
            
            # Generate new recipient wallet
            print("\n" + "=" * 60)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Generating recipient wallet...")
            wallet = generate_new_wallet()
            print(f"📍 Recipient: {wallet['address']}")
            
            # Determine network
            testnet_counter += 1
            
            if testnet_counter >= current_cycle:
                network = 'mainnet'
                testnet_counter = 0
                current_cycle = true_random_choice(CYCLE_OPTIONS)
                print(f"🔄 Next cycle: Every {current_cycle} testnet = 1 mainnet")
            else:
                network = 'testnet'
            
            print(f"🌐 Network: {network.upper()}")
            print(f"👤 Owner (gas payer): {owner_address}")
            
            # Random sleep
            sleep_duration = true_random_choice(SLEEP_PATTERNS)
            print(f"💤 Sleeping for {sleep_duration // 60}m {sleep_duration % 60}s...")
            time.sleep(sleep_duration)
            
            # Mint NFT (Owner pays gas, recipient receives NFT)
            print(f"\n🎨 Minting NFT on {network.upper()}...")
            print(f"   Owner mints → Recipient receives")
            
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
                print(f"📊 Total minted: {total_minted} | Today's mainnet: {mainnet_counter_today}/{daily_mainnet_target}")
            
            # Handle failures
            if status.startswith('FAILED'):
                if 'LOW_GAS' in status or 'NO_GAS' in status:
                    print("\n🛑 STOPPING BOT - Insufficient gas")
                    break
            
            # Periodic backup (every 100 mints)
            if total_minted % 100 == 0:
                backup_to_s3()
                
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        send_alert("🚨 Bot Crashed", f"Critical error: {str(e)}")
    finally:
        # Final backup and email
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
        
        print("\n" + "=" * 60)
        print("BOT STOPPED")
        print(f"Total minted: {total_minted}")
        print("=" * 60)

if __name__ == "__main__":
    run_bot()
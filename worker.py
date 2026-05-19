#!/usr/bin/env python3
import subprocess, psycopg2, psycopg2.extras, os, sys, signal, time, re
from datetime import datetime

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "ping_metrics")
DB_USER = os.getenv("DB_USER", "pinguser")
DB_PASS = os.getenv("DB_PASS", "pingpassword123")
WORKER_ID = os.getenv("WORKER_ID", "worker-1")
INTERVAL_MS = int(os.getenv("INTERVAL_MS", "100"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "500"))
RETRY_COUNT = int(os.getenv("RETRY_COUNT", "2"))
HOSTS_FILE = "/app/hosts.txt"

running = True
def signal_handler(sig, frame):
    global running
    print(f"[{WORKER_ID}] Shutting down...")
    running = False
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

def get_db_connection():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME,
                          user=DB_USER, password=DB_PASS, connect_timeout=10)

def parse_fping_line(line):
    line = line.strip()
    if not line: return None
    try:
        parts = line.split(" : ")
        if len(parts) < 2: return None
        target = parts[0].strip()
        rest = parts[1].strip()
        seq_start, seq_end = rest.find("["), rest.find("]")
        seq_num = int(rest[seq_start+1:seq_end]) if seq_start != -1 and seq_end != -1 else None
        if any(x in rest.lower() for x in ["timed out", "no reply", "unreachable", "error"]):
            return {"target": target, "status": "down", "rtt_ms": None, "packet_loss": 100.0, "sequence_num": seq_num}
        rtt_match = re.search(r'(\d+\.?\d*)\s+ms', rest)
        rtt = float(rtt_match.group(1)) if rtt_match else None
        loss_match = re.search(r'(\d+\.?\d*)%\s+loss', rest)
        loss = float(loss_match.group(1)) if loss_match else 0.0
        return {"target": target, "status": "up" if rtt else "down", "rtt_ms": rtt, "packet_loss": loss, "sequence_num": seq_num}
    except Exception as e:
        return None

def insert_batch(conn, batch):
    if not batch: return
    try:
        with conn.cursor() as cur:
            data = [(datetime.utcnow(), r["target"], WORKER_ID, r["status"], r["rtt_ms"], r["packet_loss"], r["sequence_num"]) for r in batch]
            psycopg2.extras.execute_values(cur, "INSERT INTO ping_metrics (time, target, worker, status, rtt_ms, packet_loss_percent, sequence_num) VALUES %s", data, page_size=len(data))
            conn.commit()
            print(f"[{WORKER_ID}] Inserted {len(batch)} rows")
    except Exception as e:
        print(f"[{WORKER_ID}] DB error: {e}")
        conn.rollback()

def main():
    print(f"[{WORKER_ID}] Starting...")
    if not os.path.exists(HOSTS_FILE):
        print(f"[{WORKER_ID}] ERROR: {HOSTS_FILE} not found!")
        sys.exit(1)
    with open(HOSTS_FILE) as f:
        host_count = sum(1 for _ in f)
    print(f"[{WORKER_ID}] Loaded {host_count} hosts")
    try:
        conn = get_db_connection()
        print(f"[{WORKER_ID}] Connected to DB")
    except Exception as e:
        print(f"[{WORKER_ID}] DB failed: {e}")
        sys.exit(1)
    cmd = ["fping", "-l", "-p", str(INTERVAL_MS), "-r", str(RETRY_COUNT), "-O", "0", "-f", HOSTS_FILE]
    print(f"[{WORKER_ID}] Running: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    batch, last_flush = [], time.time()
    try:
        for line in proc.stdout:
            if not running: break
            result = parse_fping_line(line)
            if result: batch.append(result)
            current_time = time.time()
            if len(batch) >= BATCH_SIZE or (current_time - last_flush) >= 5:
                insert_batch(conn, batch)
                batch, last_flush = [], current_time
    finally:
        if batch: insert_batch(conn, batch)
        proc.terminate()
        conn.close()
        print(f"[{WORKER_ID}] Stopped")

if __name__ == "__main__":
    main()

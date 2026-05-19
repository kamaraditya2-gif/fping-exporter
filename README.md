# 🚀 Distributed Ping Exporter → PostgreSQL/TimescaleDB

Ping 26.000+ host secara paralel menggunakan **fping**, data langsung masuk ke **PostgreSQL/TimescaleDB**.

---

## 📋 Prerequisite

- Docker & Docker Compose terinstall
- PostgreSQL 14+ dengan TimescaleDB extension (bisa install di server lain atau di host yang sama)

---

## STEP 1: Install PostgreSQL + TimescaleDB

### Opsi A: Install di Server (Bare Metal / VM)

**Ubuntu/Debian:**
```bash
# Install PostgreSQL
sudo apt update
sudo apt install -y postgresql postgresql-contrib

# Install TimescaleDB
sudo apt install -y timescaledb-postgresql-15

# Initialize TimescaleDB
sudo timescaledb-tune --quiet --yes
sudo systemctl restart postgresql
```

**CentOS/RHEL:**
```bash
# Install PostgreSQL
sudo dnf install -y postgresql15-server postgresql15-contrib
sudo /usr/pgsql-15/bin/postgresql-15-setup initdb
sudo systemctl enable --now postgresql-15

# Install TimescaleDB (lihat docs.timescale.com untuk repo)
```

### Opsi B: Install via Docker (untuk testing)

```bash
docker run -d   --name timescaledb   -e POSTGRES_DB=ping_metrics   -e POSTGRES_USER=pinguser   -e POSTGRES_PASSWORD=pingpassword123   -p 5432:5432   -v pgdata:/var/lib/postgresql/data   timescale/timescaledb:latest-pg15
```

---

## STEP 2: Setup Database

Jalankan `init.sql` sebagai superuser (postgres):

```bash
# Kalau PostgreSQL di local:
sudo -u postgres psql -f init.sql

# Kalau PostgreSQL di server lain:
psql -h YOUR_DB_HOST -U postgres -f init.sql

# Kalau via Docker:
docker exec -i timescaledb psql -U postgres -f - < init.sql
```

**Yang dilakukan init.sql:**
1. ✅ Buat database `ping_metrics`
2. ✅ Install TimescaleDB extension
3. ✅ Buat user `pinguser` dengan password
4. ✅ Buat tabel `ping_metrics` (hypertable)
5. ✅ Buat index untuk query cepat
6. ✅ Buat views untuk monitoring
7. ✅ Setup retention policy (auto hapus data > 30 hari)

---

## STEP 3: Konfigurasi Environment

Edit file `.env`:

```bash
# Database (sesuaikan dengan setup di Step 1)
DB_HOST=localhost              # IP atau hostname database
DB_PORT=5432                   # Port PostgreSQL
DB_NAME=ping_metrics           # Nama database
DB_USER=pinguser               # Username
DB_PASS=pingpassword123        # Password

# Worker config
WORKER_COUNT=4                 # Jumlah worker container
INTERVAL_MS=100                # Interval ping (ms)
BATCH_SIZE=500                 # Batch insert size
RETRY_COUNT=2                  # Retry kalau ping gagal
```

---

## STEP 4: Siapkan Target Hosts

Bagi 26.000 target ke file `hosts-worker-*.txt`:

```
hosts-worker-1.txt   → 8000 hosts
hosts-worker-2.txt   → 8000 hosts
hosts-worker-3.txt   → 5000 hosts
hosts-worker-4.txt   → 5000 hosts
```

**Format:** Satu IP atau hostname per baris

```
8.8.8.8
1.1.1.1
192.168.1.1
server1.example.com
...
```

**Tips:**
- Ganti sample IPs dengan target kamu
- Bisa pakai script untuk split file besar:
```bash
# Split file hosts.txt ke 4 bagian
split -l 8000 hosts.txt hosts-worker-
# Rename sesuai format
```

---

## STEP 5: Build & Run

```bash
# 1. Build image worker
docker compose -f docker-compose.yml -f docker-compose.workers.yml build

# 2. Jalankan semua worker (4 worker sesuai .env)
docker compose -f docker-compose.yml -f docker-compose.workers.yml up -d

# 3. Cek status
docker compose -f docker-compose.yml -f docker-compose.workers.yml ps

# 4. Lihat logs real-time
docker compose -f docker-compose.yml -f docker-compose.workers.yml logs -f
```

---

## STEP 6: Verifikasi Data Masuk

Connect ke PostgreSQL dan cek:

```bash
psql -h YOUR_DB_HOST -U pinguser -d ping_metrics
```

```sql
-- Cek data masuk
SELECT COUNT(*) FROM ping_metrics;

-- Cek status terakhir
SELECT * FROM v_ping_latest LIMIT 10;

-- Cek target yang down
SELECT target, worker, last_seen FROM v_ping_latest WHERE status = 'down';

-- Cek uptime 24 jam
SELECT * FROM v_ping_uptime_24h WHERE uptime_percent < 100;
```

---

## 📊 Grafana Dashboard (Opsional)

```bash
# Jalankan Grafana
docker compose -f docker-compose.yml --profile grafana up -d
```

Buka: http://localhost:3000
- Username: `admin`
- Password: `admin123`

Dashboard sudah auto-provisioned dengan datasource PostgreSQL.

---

## 🔧 Scale Worker

```bash
# Tambah worker 5 (buat file hosts-worker-5.txt dulu)
docker compose -f docker-compose.yml -f docker-compose.workers.yml up -d fping-worker-5

# Stop semua worker
docker compose -f docker-compose.yml -f docker-compose.workers.yml stop

# Hapus semua worker
docker compose -f docker-compose.yml -f docker-compose.workers.yml down
```

---

## 🛠️ Troubleshooting

### Permission denied ICMP
```bash
# Di host Docker:
sudo sysctl -w net.ipv4.ping_group_range="0 2147483647"
# Atau tambahkan ke /etc/sysctl.conf untuk permanent
```

### Worker exit karena hosts file tidak ada
Pastikan `hosts-worker-N.txt` ada untuk setiap worker yang dijalankan.

### DB connection failed
- Cek firewall: port 5432 harus terbuka dari Docker host ke DB server
- Cek `pg_hba.conf`: tambahkan rule untuk IP Docker host
- Cek `.env`: pastikan DB_HOST, DB_USER, DB_PASS benar

### Data tidak masuk
```bash
# Cek logs worker
docker logs fping_worker_1

# Cek koneksi DB dari container
docker exec -it fping_worker_1 python -c "
import psycopg2
conn = psycopg2.connect(host='YOUR_DB_HOST', port=5432, database='ping_metrics', user='pinguser', password='pingpassword123')
print('Connected!')
conn.close()
"
```

---

## 📁 Struktur File

```
.
├── .env                          # ⭐ Konfigurasi utama
├── docker-compose.yml            # Base compose (grafana)
├── docker-compose.workers.yml    # Worker services
├── Dockerfile                    # Build image worker
├── worker.py                     # Script worker
├── init.sql                      # Setup DB (jalanin sekali)
├── hosts-worker-1.txt            # Target worker 1
├── hosts-worker-2.txt            # Target worker 2
├── hosts-worker-3.txt            # Target worker 3
├── hosts-worker-4.txt            # Target worker 4
├── README.md                     # Ini
└── grafana/
    ├── datasources/
    │   └── postgres.yml          # Auto datasource
    └── dashboards/
        ├── dashboard.yml         # Dashboard provider
        └── ping-dashboard.json   # Sample dashboard
```

---

## 🎯 Query Berguna

```sql
-- Jumlah data per jam
SELECT time_bucket('1 hour', time) AS hour, COUNT(*) 
FROM ping_metrics 
GROUP BY hour ORDER BY hour DESC;

-- Top 10 target dengan packet loss tertinggi
SELECT target, AVG(packet_loss_percent) as avg_loss
FROM ping_metrics 
WHERE time > NOW() - INTERVAL '1 hour'
GROUP BY target 
ORDER BY avg_loss DESC 
LIMIT 10;

-- Worker performance
SELECT * FROM v_worker_stats;
```

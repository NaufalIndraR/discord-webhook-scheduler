# Discord Multi-Channel Message Scheduler

Otomatisasi pengiriman pesan promosi/trading berkala ke **BANYAK channel Discord** dengan **Waktu Independen Murni (True Independent Timings)** menggunakan **Async Multi-Tab Playwright Chromium**.

Didesain khusus untuk menghindari deteksi bot dan larangan akun (*ban*) dengan menggunakan browser Google Chrome asli, tanpa mengambil alih atau menggerakkan kursor mouse fisik (*Zero Cursor Hijacking*).

---

## Fitur Utama

- **Live TUI Dashboard (ANSI Colors & In-Place Redraw)**:
  - Tampilan terminal modern bergaya TUI (*Terminal User Interface*) dengan tabel status presisi.
  - Menggunakan teknik ANSI cursor positioning (`\033[H`) dan line clearing (`\033[K`) sehingga layar tidak berkedip (*flicker-free*) dan tidak mencetak baris berulang-ulang ke bawah.
  - **Zero Emoji**: 100% menggunakan badge status teks bersih (`[READY]`, `[SENDING]`, `[COOLDOWN]`, `[SLOWMODE]`, `[OK]`, `[WAIT]`) yang aman dari error encoding terminal.
  - Live ticking countdown timer: hitungan mundur detik diperbarui secara real-time di tabel.
- **True Independent Timings (Single-Tab Ultra-Low RAM Architecture)**:
  - Menggunakan 1 tab browser bersama (*Single-Tab Reuse*) dengan antrean asinkron independen untuk setiap channel.
  - Sangat hemat RAM (~120 MB RAM vs 1.2 GB+), dirancang khusus agar stabil di VPS/Docker dengan RAM 1–2 GB tanpa membebani server atau menyebabkan crash.
  - Setiap channel berjalan di **asynchronous worker loop sendiri** dengan timer hitung mundur independen.
- **Real-Time WebSocket Slowmode Sync**:
  - Karena tiap tab tetap terbuka, Discord WebSocket membaca hitungan mundur slowmode secara presisi langsung dari server Discord.
  - Jika Channel 1 terkena slowmode 10 menit, Channel 2 dan Channel 3 tetap berjalan lancar sesuai interval masing-masing (misal tiap 5 detik atau 1 jam).
- **Independent Hot-Reload Messages (`msg1.txt`, `msg2.txt`, `msg3.txt`)**:
  - Setiap channel memiliki file teksnya sendiri. Anda bisa mengedit teks/harga saat script berjalan (*runtime*) tanpa perlu restart program.
- **No-GUI by Default (Zero Distraction)**:
  - Secara default berjalan tersembunyi di latar belakang.
  - Otomatis memunculkan jendela ke layar jika Anda ter-logout / butuh scan QR code, lalu otomatis bersembunyi kembali setelah login selesai.
  - Gunakan flag `--gui` jika ingin melihat jendela secara manual.
- **Concurrency Safety Lock**:
  - Pengetikan pesan diproteksi antrean mikro-detik (*asyncio lock*) agar input keyboard tidak pernah bertabrakan meskipun 2 channel selesai cooldown di detik yang sama.

---

## Struktur File Pesan

```text
discord-webhook-scheduler/
├── msg1.txt                # Pesan untuk Channel 1 (BHZR Items)
├── msg2.txt                # Pesan untuk Channel 2 (WL Buying)
├── msg3.txt                # Pesan untuk Channel 3 (Seeds & Blocks)
├── config.json             # Konfigurasi daftar channel & interval
├── main.py                 # Skrip utama otomatisasi (Async Multi-Tab + TUI)
└── README.md               # Dokumentasi
```

---

## Konfigurasi Channel (`config.json`)

Contoh konfigurasi 3 channel dengan file pesan dan interval masing-masing:

```json
{
  "channels": [
    {
      "name": "Channel 1 (BHZR Items)",
      "channel_url": "https://discord.com/channels/1554664263937695864/1554664264390672445",
      "message_file": "msg1.txt",
      "interval_seconds": 5,
      "jitter_seconds": 0
    },
    {
      "name": "Channel 2 (WL Buying)",
      "channel_url": "https://discord.com/channels/1554664263937695864/1554669233747656794",
      "message_file": "msg2.txt",
      "interval_seconds": 5,
      "jitter_seconds": 0
    },
    {
      "name": "Channel 3 (Seeds & Blocks)",
      "channel_url": "https://discord.com/channels/1554664263937695864/1554664264390672446",
      "message_file": "msg3.txt",
      "interval_seconds": 5,
      "jitter_seconds": 0
    }
  ]
}
```

---

## Cara Menjalankan

### Mode Latar Belakang (Default / No-GUI)
```powershell
python main.py
```

### Mode Tampil Jendela (GUI)
```powershell
python main.py --gui
```

---

## Manajemen Banyak Akun (Multi-Account)

### 1. Menggunakan Profil Terpisah (Rekomendasi)
Anda dapat menyimpan banyak akun secara permanen tanpa perlu login ulang bolak-balik:

- **Akun Utama:**
  ```powershell
  python main.py
  ```
- **Akun Kedua (Alt 1):**
  ```powershell
  python main.py --profile alt1
  ```
- **Akun Ketiga (Alt 2):**
  ```powershell
  python main.py -p alt2
  ```
*Browser akan otomatis membuka jendela login sekali saja saat profil baru dibuat. Setelah login, sesi akun tersebut tersimpan selamanya.*

### 2. Ganti Akun pada Profil Saat Ini
Jika ingin logout dan login dengan akun baru pada profil yang sedang aktif:
```powershell
python main.py --switch-account
```
*(Atau `python main.py -p alt1 --switch-account` untuk profil tertentu).*

### 3. Logout Manual di Jendela Browser
Jalankan dengan mode tampilan:
```powershell
python main.py --gui
```
Lalu klik tombol Settings -> Log Out langsung di antarmuka Discord.

---

## Cara Menghentikan Program

Tekan **`Ctrl + C`** di jendela terminal kapan saja. Browser akan ditutup dengan rapi dan sesi login Anda tetap tersimpan.
 
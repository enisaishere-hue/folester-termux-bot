# Folester Termux Auto-Buy

Bot auto-buy untuk **Folester Frames testnet** (https://www.folester.xyz/play),
jalan di **Termux di HP Android**. Begitu ada Frame (token) baru, bot langsung
beli pakai saldo `$ANUL` simulasi — bukan SOL asli, bukan transaksi blockchain.

## Cara pakai (tanpa perintah panjang)

```sh
python3 atur.py   # jawab pertanyaan (Enter = pakai nilai lama), tersimpan di config.json
mulai             # bot jalan (otomatis update + matikan bot lama dulu)
log               # lihat log live (Ctrl+C buat keluar)
pkill -f bot.py   # berhenti
```

`mulai` bisa diketik dari mana saja, tanpa `cd` dan tanpa `./` — pasang
sekali saja dengan `sh pasang` (setelah `git pull` pertama yang membawa
versi ini):

```sh
cd ~/folester-termux-bot && git pull
sh pasang
source ~/.bashrc
mulai
```

`pasang` membuat pembungkus di `~/bin` yang menjalankan `mulai` lewat
`sh`, jadi tidak tergantung izin eksekusi file di repo. Jangan pasang
dengan symlink (`ln -sf .../mulai ~/bin/mulai`): file `mulai` di repo
tidak punya izin eksekusi (mode 100644), jadi symlink-nya ikut gagal
dengan "Permission denied". `pasang` juga TIDAK memberi +x pada file repo
— dulu itu dilakukan supaya `./mulai` bisa dipakai, tapi `chmod +x` itu
mengotori repo sehingga `git pull` berikutnya selalu gagal "Your local
changes to mulai/mulai2 would be overwritten" (lingkaran yang terjadi
21 Nov). Kalau `git pull` gagal begitu, perbaikannya: `git checkout --
mulai mulai2` lalu `git pull` lagi, atau jalankan `sh pasang` (versi baru
membersihkan perubahan mode itu sendiri). `./mulai` langsung tetap akan
"Permission denied" — pakai `mulai` (wrapper) atau `sh mulai`.

Kalau `mulai` kelihatan diam, jangan langsung `Ctrl+C` — tunggu sampai
muncul `Bot jalan (PID ...)`, paling lama ~12 detik. `git pull`-nya jalan
di background dengan titik kemajuan tiap detik dan batas keras 10 detik
(murni shell, tidak butuh perintah `timeout`): kalau lewat, bot tetap jalan
pakai versi lokal. Penyebab stuck lama: `git pull` tanpa `timeout` yang
terpasang di Termux jalan tanpa batas waktu sama sekali. Cara lama tetap
bisa: `cd ~/folester-termux-bot && ./mulai`.

## Perbaikan 18 Nov 2026 — bot kadang gagal beli

Diagnosis dari screenshot log 18 Nov 21:58 WIB + kode bot:

- **Saldo server sudah −59.514,19 ANUL saat bot itu start** (proses itu beli 0,
  jadi bukan dia yang menghabiskan). Dengan saldo negatif, bot versi lama
  langsung **keluar diam-diam** begitu Frame baru pertama muncul (cek
  reserve gagal → STOP → exit). Itu yang terlihat seperti "kadang tidak
  bisa membeli". Di jendela screenshot sendiri (14:43–14:58 WIB) tidak ada
  Frame baru sama sekali — TRUMP adalah Frame terbaru dan umurnya terus
  bertambah 91 → 953 dtk — jadi beli 0 di situ normal, bukan gagal.
- **Penyebab saldo bisa negatif / terkuras:** `mulai` lama mematikan bot
  dengan `pkill -f "python3 bot.py$"` — pola itu **tidak cocok** dengan bot
  yang dijalankan pakai flag (mis. `python3 bot.py --keypair ...`), jadi bot
  lama tetap jalan dan dua/tiga bot membeli bersamaan di wallet yang sama,
  rebutan cookie sesi, dan menguras saldo yang sama.

Yang diperbaiki di versi ini:

1. **STOP jadi JEDA, bukan mati.** Saldo/reserve/budget/max_buys habis →
   bot tetap memantau, tulis `JEDA BELI: ...` di log, refresh saldo dari
   server tiap 60 dtk, dan beli jalan lagi sendiri kalau saldo pulih
   (mis. kamu jual posisi manual). Frame yang muncul saat jeda tetap
   diantre sampai umurnya lewat max_age.
2. **Login ulang boleh tiap percobaan trade.** Sebelumnya sesi yang habis
   kedua kalinya membuat semua beli berikutnya gagal `sign_in_required`
   selamanya (flag reauth cuma sekali seumur hidup bot).
3. **Saldo 0 tidak lagi salah dibaca** (bug `or`: 0 dianggap tidak ada).
   Saldo negatif dari server kini diperingatkan jelas di awal log.
4. **Satu proses per wallet (file lock).** Bot kedua dengan wallet sama
   menolak jalan dengan pesan jelas — tidak ada lagi beli dobel.
5. **`launch_wait` tidak lagi dicoba tiap 0,5 dtk.** Server baru buka
   trading umur 30 dtk, jadi retry pertama dijadwalkan umur 30,5 dtk —
   ~60 POST sia-sia per Frame hilang, risiko kena `trade_cooldown` /
   rate-limit mengecil.
6. **Gagal beli sesaat (jaringan, 5xx, rate-limit) diantre ulang** sampai
   umur max_age, bukan dibuang padahal Frame sudah ditandai seen.
7. **WebSocket timeout 5 → 30 dtk** (di HP/VPN jeda >5 dtk itu biasa;
   log lama penuh `websocket putus (Errno 103/104)`).
8. **`mulai`/`mulai2` benar-benar mematikan bot lama** (file PID + nama
   file cookie + pola lama), dan `mulai` kini menjalankan bot dengan
   `--cookies` eksplisit supaya bisa dimatikan lagi.

**Kalau saldomu masih negatif / di bawah reserve:** bot versi baru tidak
akan beli sampai saldo pulih — itu sengaja. Cek dashboard Folester, jual
posisi manual sampai saldo di atas reserve + amount sekali beli, bot akan
lanjut sendiri tanpa restart. Kalau saldo negatifnya tidak masuk akal
(mis. kamu tidak pernah beli sebanyak itu), cek juga `ps` di Termux —
pastikan cuma satu bot yang jalan: `ps aux | grep bot.py`.

`config.json` berisi pengaturanmu (file keypair, ANUL per beli, delay beli,
delay jual, dst.) dan tidak ikut ke Git — aman dari `git pull`. Semua nilai
di `config.json` bisa ditimpa lewat flag kalau mau, mis.
`python3 bot.py --amount 50` (berlaku sekali jalan itu saja).

## Dua akun sekaligus

```sh
./mulai    # bot utama (wallet di config.json), log: log
./mulai2   # bot akun kedua (AKG8, keypair ~/bacj-key.txt), log: log2
```

Bot kedua memakai pengaturan yang sama dari `config.json`, tapi keypair dan
file cookie sesi sendiri (`~/.folester_session_cookies-akg8.txt`) supaya
sesi kedua akun tidak saling menimpa. `./mulai` hanya mematikan bot utama,
`./mulai2` hanya mematikan bot akun kedua — keduanya bisa jalan bersamaan.
Pasang alias log kedua sekali saja:

```sh
echo "alias log2='tail -f ~/folester-termux-bot/folester-akg8.log'" >> ~/.bashrc && source ~/.bashrc
```

Berhenti: `pkill -f "python3 bot.py$"` (utama) atau `pkill -f bacj-key.txt`
(akun kedua).

**File keypair = path file, bukan key-nya langsung.** Kalau pakai wallet
beda, simpan dulu key-nya ke file baru, lalu isi path itu di `atur.py`:

```sh
cat > ~/wallet-baru-key.txt   # tempel key-nya, Enter, Ctrl+D
python3 atur.py               # isi path: ~/wallet-baru-key.txt
```

Jangan pernah tempel private key ke `atur.py` atau ke chat — bot dan
`atur.py` akan menolaknya dan menyuruh simpan ke file dulu.

## Cara kerja

1. Baca keypair Solana dari HP kamu sendiri (mis. `~/.config/solana/id.json`).
2. Minta nonce ke Folester, tanda tangani **pesan login gratis**
   (`folester.xyz wants you to sign in...`), verifikasi, dapat cookie sesi.
3. Cek syarat kelayakan wallet (umur, hari aktif, transaksi, saldo SOL),
   lalu join kalau belum terdaftar.
4. Deteksi Frame baru lewat **websocket live** (`/api/live`, jalur utama):
   begitu ada trade pertama di Frame baru, server mengirimnya kurang dari
   ~1 detik setelah Frame dibuat, dan bot langsung beli **100 ANUL**.
   Kalau websocket putus, bot menyambung lagi sendiri, dan **polling daftar
   Frame tiap 30 detik** tetap jalan sebagai cadangan. Berhenti setelah
   50 kali beli, total 5.000 ANUL, atau saldo di bawah 100 ANUL. Kalau
   jaringan gagal sesaat (DNS, timeout, server sibuk), tiap request dicoba
   ulang 5x sebelum bot menyerah. Semua request HTTP memakai Python murni
   (tanpa library tambahan); curl dipakai sebagai cadangan kalau jalur
   Python gagal. Bot juga menulis kabar berkala tiap
   3 detik di log (cek ke-berapa, Frame terbaru, jumlah beli, saldo, status
   websocket) supaya kelihatan masih jalan; intervalnya bisa diubah dengan
   `--heartbeat` (0 = mati). Opsi `--no-ws` mematikan websocket (cuma polling).

## Paket data

Daftar Frame ~1 MB per unduhan (dikompres jadi ~0,35 MB). Karena deteksi
cepat sudah lewat websocket (pesannya kecil), polling cuma cadangan tiap
30 detik — total pemakaian kira-kira **50 MB/jam**. Dulu polling tiap
0,5 detik bisa makan 2-4 GB/jam. Kalau mau lebih hemat, naikkan
`--interval` (mis. 60); kalau mau lebih cepat saat websocket putus,
turunkan.

## Instal di Termux

```sh
pkg install python
curl -sL https://raw.githubusercontent.com/enisaishere-hue/folester-termux-bot/main/bot.py -o bot.py
```

Atau pakai git:

```sh
pkg install python git
git clone https://github.com/enisaishere-hue/folester-termux-bot.git
cd folester-termux-bot
```

## Siapkan keypair dulu (sekali saja)

Script butuh keypair wallet BacJ di HP kamu. Kalau belum ada file
`~/.config/solana/id.json` di Termux, export dari Phantom:

1. Buka Phantom, pilih wallet BacJ.
2. Settings → Export Private Key, masukkan password, salin kuncinya.
3. Di Termux, simpan ke file (tempel, Enter, lalu Ctrl+D):

```sh
cat > ~/bacj-key.txt
chmod 600 ~/bacj-key.txt
```

File itu cuma ada di HP kamu — jangan kirim ke siapa pun.

## Pakai

Cek dulu tanpa beli — pastikan alamat yang tampil adalah wallet kamu
(`BacJgMh1bS4yPYKA6oLMZUWrwgeDE6aJQdAZhKiu399C`):

```sh
python3 bot.py --keypair ~/bacj-key.txt --check-only
```

Kalau keypair kamu sudah ada sebagai file JSON, pakai path itu:

```sh
python3 bot.py --keypair ~/.config/solana/id.json --check-only
```

Jalankan:

```sh
termux-wake-lock
nohup python3 bot.py --keypair ~/.config/solana/id.json --amount 100 > folester.log 2>&1 &
```

Berhenti:

```sh
pkill -f bot.py
```

Opsi lain: `--amount 100` (ANUL per Frame), `--interval 30` (detik antar cek
polling cadangan), `--no-ws` (matikan websocket), `--max-buys 50`, `--budget 5000`,
`--reserve 100`, `--max-age 120`, `--buy-delay 0.5` (beli saat Frame berumur
0,5 detik setelah launch), `--launch-wait-retry 0.5` (jeda detik antar coba ulang
saat server bilang `launch_wait`), `--auto-sell-delay 0` (jual otomatis mati;
isi 10 untuk hidupkan lagi), `--cookies FILE` (file cookie sesi, wajib
beda tiap akun kalau jalan 2 bot sekaligus), `--once` (cek sekali),
`--check-only` (cuma login + cek saldo).

## Auto-sell (mati secara default)

Auto-sell saat ini **mati** (`--auto-sell-delay 0`). Kalau mau dihidupkan
lagi, jalankan bot dengan `--auto-sell-delay 10`: setelah beli berhasil,
bot otomatis menjual lagi 10 detik kemudian — semua token yang didapat
dari beli itu — supaya modal kembali dan bisa dipakai beli Frame
berikutnya. Jual tidak melihat harga: kalau harga turun dalam 10 detik
itu, jualnya rugi (plus fee 2x). Kalau posisi terkunci sebagian oleh
server, bot menjual sebanyak yang bisa dijual; kalau terkunci semua, bot
coba lagi tiap 5 detik sampai 5 menit, lewat dari itu posisi ditahan dan
harus dijual manual.

Dua aturan server yang perlu diketahui (dari kode situs Folester sendiri):
trading baru dibuka **30 detik** setelah Frame dibuat — jadi beli di umur
0,5 detik itu selalu ditolak dulu (`launch_wait`), bot coba lagi tiap
0,5 detik sampai umur 30 detik baru berhasil. Dan ada jeda **2 detik**
antar trade (`trade_cooldown`); kalau kena, bot menunggu 2,1 detik
sebelum coba lagi.

## 2 akun sekaligus

Jalankan 2 proses — masing-masing dengan file keypair, file cookie, dan file
log sendiri:

```sh
# File ~/bacj-key.txt yang lama isinya key AKG8 — ganti nama dulu:
mv ~/bacj-key.txt ~/akg8-key.txt
# Export key BacJ dari Phantom, simpan ke ~/bacj-key.txt (jangan kirim ke siapa pun)
pkill -f bot.py
cd ~/folester-termux-bot && git pull
nohup python3 bot.py --keypair ~/akg8-key.txt --amount 100 --cookies ~/.folester-akg8.txt > folester-akg8.log 2>&1 &
nohup python3 bot.py --keypair ~/bacj-key.txt --amount 100 --cookies ~/.folester-bacj.txt > folester-bacj.log 2>&1 &
```

Cek tiap bot: `tail -f folester-akg8.log` / `tail -f folester-bacj.log` —
pastikan baris `wallet=...` di tiap log cocok dengan akunnya. Kalau
`--cookies`-nya sama, sesi kedua bot saling timpa dan keduanya login melulu.
Sebelum jalanin akun baru, cek dulu alamatnya:
`python3 bot.py --keypair ~/bacj-key.txt --check-only`.

## Keamanan

- **Keypair tidak pernah dikirim ke mana pun.** Script cuma membacanya di HP
  kamu. Jangan pernah kirim keypair / seed phrase ke siapa pun, termasuk ke
  pembuat script ini.
- Script tidak pernah mencetak isi keypair ke log — yang tampil cuma alamat
  wallet (publik).
- Pesan yang ditandatangani dicek dulu: harus pesan login Folester, bukan yang
  lain. Script tidak menandatangani transaksi apa pun.

## Syarat wallet

Wallet yang dipakai harus lolos syarat Folester: umur ≥ 90 hari, ≥ 20 hari
aktif, ≥ 50 transaksi, saldo ≥ 0,01 SOL. **Wallet baru tidak bisa join** —
pakai wallet Solana lamamu.

## Risiko

- Terms Folester §11 melarang bot/script. Kalau ketahuan, alokasi airdrop bisa
  dibatalkan, dihapus dari leaderboard, atau wallet diblokir.
- "Pembeli pertama" tidak bisa dijamin: trade pertama sebuah Frame mendarat
  ~1 detik setelah dibuat (biasanya AI trader situs / kreator), dan bot
  membeli 0,5 detik setelah Frame dibuat — jadi bot biasanya pembeli
  ke-2/ke-3, bukan ke-1. Kalau server masih bilang `launch_wait`, bot coba
  lagi tiap 0,5 detik sampai umur Frame 120 detik.
- Script ini cuma BELI. Jual tetap manual dari HP.

## Lisensi

MIT. Pakai dengan risiko sendiri.

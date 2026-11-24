#!/usr/bin/env python3
# ============================================================================
# Folester Frames TESTNET auto-buy — Termux (jalan di HP Berly, BUKAN di server)
# ============================================================================
# CARA PAKAI (tanpa perintah python yang panjang)
#   1. python3 atur.py — jawab pertanyaan (berapa ANUL tiap beli, beli
#      berapa detik setelah launch, jual berapa detik setelah beli, dst.).
#      Tersimpan di config.json. Tekan Enter = pakai nilai lama.
#   2. ./mulai — bot jalan (otomatis update dari GitHub + matikan bot lama).
#   3. log — lihat log live.  pkill -f bot.py — berhenti.
#   Kalau mau tetap pakai perintah langsung, semua pengaturan di config.json
#   bisa ditimpa lewat flag, mis. python3 bot.py --amount 50 (sekali jalan).
#
# CARA KERJA
#   Script ini jalan di Termux di HP kamu sendiri. Dia memantau daftar Frame
#   baru di folester.xyz/play, dan kalau ada Frame baru langsung beli pakai
#   saldo $ANUL simulasi (testnet). TIDAK ADA SOL asli yang dipakai, TIDAK ADA
#   transaksi blockchain. Yang ditandatangani cuma SATU pesan login gratis
#   ("folester.xyz wants you to sign in...") — bukan transaksi, tanpa gas.
#   Deteksi Frame baru ada DUA jalur (keduanya cuma baca, tanpa login):
#     1. WebSocket live /api/live — jalur UTAMA. Begitu ada trade pertama di
#        Frame baru, server mengirimnya kurang dari ~1 detik setelah Frame
#        dibuat (terverifikasi live 2026-11-15: trade pertama SOL mendarat
#        1,1 detik setelah launching). Bot beli tepat 0,5 detik setelah
#        Frame dibuat (--buy-delay): kalau Frame terdeteksi lebih cepat,
#        bot menunggu sampai umurnya 0,5 detik dulu baru beli. Kalau server
#        menolak dengan launch_wait (trading Frame itu belum dibuka), bot
#        coba lagi tiap 0,5 detik sampai umur Frame 120 detik.
#   PENTING — aturan server Folester (dari kode situsnya sendiri):
#     * Trading baru dibuka 30 detik setelah Frame dibuat. Jadi beli di
#       umur 0,5 detik itu SELALU ditolak dulu (launch_wait); bot coba lagi
#       tiap 0,5 detik sampai umur 30 detik, baru berhasil beli.
#     * Ada jeda 2 detik antar trade (trade_cooldown). Kalau kena, bot
#       menunggu 2,1 detik sebelum coba lagi.
#   Auto-sell MATI secara default (--auto-sell-delay 0). Kalau mau dihidupkan
#   lagi: --auto-sell-delay 10 — bot menjual semua token hasil beli 10 detik
#   kemudian supaya modal kembali. Jual tidak melihat harga: kalau harga
#   turun dalam 10 detik itu, jualnya rugi.
#     2. Polling daftar Frame tiap 30 detik — jalur CADANGAN. Kalau websocket
#        putus, polling tetap jalan, jadi bot tidak pernah buta. Websocket
#        yang putus disambung lagi otomatis (backoff 1-30 dtk).
#   Bot jalan TERUS (nonstop) sampai batas aman tercapai:
#   50 kali beli / total 5.000 ANUL / saldo di bawah 100 ANUL.
#
# PERBAIKAN 2026-11-18 (gagal beli, dari screenshot log 18 Nov 21:58 WIB):
#   1. STOP karena saldo/reserve/budget/max_buys TIDAK LAGI mematikan bot:
#      bot JEDA beli, tetap memantau, refresh saldo tiap 60 dtk, dan lanjut
#      otomatis kalau saldo pulih (mis. habis jual posisi manual). Sebelumnya
#      bot keluar diam-diam saat Frame baru pertama muncul sesudah saldo
#      habis — itu yang terlihat seperti "kadang tidak bisa membeli".
#   2. Login ulang (reauth) sekarang boleh tiap percobaan trade, bukan cuma
#      sekali seumur hidup bot: sebelumnya sesi yang habis kedua kalinya
#      membuat SEMUA beli berikutnya gagal sign_in_required.
#   3. Saldo 0 dari server tidak lagi salah dibaca (bug `or`: 0 dianggap
#      tidak ada, lalu dipakai saldo-amount). Saldo negatif dari server
#      dilaporkan jelas di awal, bukan cuma di heartbeat.
#   4. Satu proses per wallet (file lock): bot kedua dengan wallet sama
#      menolak jalan, jadi tidak ada lagi beli dobel / saldo terkuras
#      bersamaan gara-gara `mulai` gagal mematikan bot lama.
#   5. launch_wait tidak lagi dicoba tiap 0,5 dtk sejak umur 0,5 dtk
#      (~60 POST sia-sia): server baru buka trading umur 30 dtk, jadi
#      retry pertama dijadwalkan umur 30,5 dtk. Lebih hemat request dan
#      kecil risiko kena trade_cooldown / rate-limit.
#   6. Gagal beli sesaat (jaringan, 5xx, rate-limit, insufficient_balance)
#      sekarang diantre ulang sampai umur max_age, bukan dibuang begitu
#      saja padahal Frame sudah ditandai seen.
#   7. WebSocket timeout 5 -> 30 dtk: di HP/VPN jeda >5 dtk itu biasa dan
#      sebelumnya memutus WS berkali-kali (Errno 103/104 di log).
#   8. buy_delay tidak lagi tidur blokir di loop utama: Frame yang
#      terdeteksi terlalu dini dijadwalkan ke antrean, deteksi Frame baru
#      tetap jalan.
#
# KUNCI TETAP DI HP KAMU
#   Script ini membaca file keypair Solana dari HP kamu sendiri dan TIDAK
#   PERNAH mengirimnya ke mana pun. Dua format diterima:
#     1. File keypair Solana (JSON, mis. ~/.config/solana/id.json)
#     2. File berisi SATU BARIS private key base58 — hasil export dari Phantom
#        (buka Phantom, pilih wallet BacJ, Settings > Export Private Key).
#        Simpan ke file dengan:  cat > ~/bacj-key.txt  (lalu tempel, Enter, Ctrl+D)
#        lalu jalankan script dengan --keypair ~/bacj-key.txt
#   Jangan pernah kirim file keypair / seed phrase itu ke saya, ke chat,
#   ke Drive, atau ke siapa pun. Script ini juga tidak pernah mencetak
#   isi keypair ke log — yang tampil cuma alamat wallet (publik).
#
# RISIKO YANG SUDAH DIKETAHUI (baca dulu sebelum jalanin)
#   - Terms Folester §11 melarang bot/script. Kalau ketahuan, alokasi
#     airdrop bisa dibatalkan, dihapus dari leaderboard, atau wallet diblokir.
#     Poin dibagikan manual tiap minggu; 150 jt $ANUL direncanakan untuk
#     Airdrop 2 tapi konversinya belum diputuskan.
#   - Auto-sell tidak melihat harga: 10 detik setelah beli, bot menjual
#     apa pun harganya. Kalau harga turun, modal kembali lebih kecil dari
#     100 ANUL (rugi + fee 2x). Kalau naik, untung. Posisi juga bisa
#     terkunci sebagian oleh server — kalau begitu bot menjual sebanyak
#     yang bisa dijual, sisanya ditahan.
#   - "Pembeli pertama" tidak bisa dijamin: trade pertama sebuah Frame
#     mendarat ~1 detik setelah dibuat (biasanya AI trader situs / kreator),
#     dan bot membeli 0,5 detik setelah Frame dibuat — jadi bot biasanya
#     pembeli ke-2/ke-3, bukan ke-1. Kalau server masih bilang launch_wait,
#     bot coba lagi tiap 0,5 detik sampai umur Frame 120 detik. Polling saja
#     lebih lambat (tiap 30 detik).
#   - Script ini cuma BELI. Jual tetap manual dari HP kamu.
#   - Wallet yang dipakai HARUS lolos 3 dari 4 syarat Folester: umur >=90 hari,
#     >=20 hari aktif, >=50 transaksi, saldo >=0,01 SOL. Wallet baru TIDAK
#     lolos — pakai wallet Solana lamamu.
#
# KEBUTUHAN DI TERMUX (sekali saja):
#   pkg install python
#   (curl opsional — dipakai sebagai cadangan kalau HTTP Python gagal)
#
# CARA JALANIN (ketik di Termux, satu baris tiap perintah):
#   1. Cek dulu (tanpa beli):  python3 bot.py --keypair ~/.config/solana/id.json --check-only
#   2. Jalanin beneran:       python3 bot.py --keypair ~/.config/solana/id.json --amount 100
#   3. Biar tetap jalan saat layar mati:  termux-wake-lock
#      lalu jalankan dengan:  nohup python3 bot.py --keypair ~/.config/solana/id.json --amount 100 > folester.log 2>&1 &
#   4. Berhenti:  pkill -f bot.py
#
# 2 AKUN SEKALIGUS (mis. BacJ + AKG8): jalankan 2 proses, masing-masing
# dengan file keypair, file cookie, dan file log sendiri:
#   mv ~/bacj-key.txt ~/akg8-key.txt   (file lama isinya key AKG8)
#   (export key BacJ dari Phantom, simpan ke ~/bacj-key.txt)
#   nohup python3 bot.py --keypair ~/akg8-key.txt --amount 100 --cookies ~/.folester-akg8.txt > folester-akg8.log 2>&1 &
#   nohup python3 bot.py --keypair ~/bacj-key.txt --amount 100 --cookies ~/.folester-bacj.txt > folester-bacj.log 2>&1 &
# Cek tiap bot: tail -f folester-akg8.log  /  tail -f folester-bacj.log
# Pastikan baris "wallet=..." di tiap log cocok dengan akunnya.
#
# OPSI (boleh diubah):
#   --amount 100     = beli 100 ANUL tiap Frame baru (minimal 1)
#   --interval 30    = cek daftar Frame tiap 30 detik (jalur polling cadangan)
#   --no-ws          = matikan websocket, cuma pakai polling (kalau WS bermasalah)
#   --max-buys 50    = berhenti setelah 50 kali beli
#   --budget 1000000000 = batas total belanja (default praktis tanpa batas;
#       atur.py tidak lagi menanyakan budget sejak 22 Nov 2026)
#   --reserve 100    = berhenti kalau saldo ANUL di bawah 100
#   --max-age 120    = cuma beli Frame yang umurnya <=120 detik saat ketemu
#   --buy-delay 0.5  = beli saat Frame berumur 0,5 detik setelah launch
#   --launch-wait-retry 0.5 = jeda detik antar coba ulang saat server bilang launch_wait
#   --auto-sell-delay 0 = jual otomatis mati (isi 10 untuk hidupkan lagi)
#   --cookies FILE   = file cookie sesi (default ~/.folester_session_cookies.txt).
#                      WAJIB beda tiap akun kalau jalan 2 bot sekaligus —
#                      kalau sama, sesinya saling timpa dan bot login melulu.
#   --once           = cek sekali lalu keluar (buat ngetes)
#   retry otomatis    = kalau jaringan gagal sesaat (DNS/timeout/server sibuk),
#                       tiap request dicoba ulang 5x sebelum bot menyerah
#   --heartbeat 3    = kabar berkala tiap 3 detik di log (bukti bot masih jalan)
# PAKET DATA: daftar Frame ~1 MB per unduhan (dikompres jadi ~0,35 MB).
# Dulu polling tiap 0,5 dtk bisa makan 2-4 GB/jam. Sekarang deteksi cepat
# sudah lewat websocket (pesannya kecil, ~1,5 dtk), polling cuma cadangan
# tiap 30 dtk — total pemakaian kira-kira 50 MB/jam. Kalau mau lebih hemat,
# naikkan --interval (mis. 60); kalau mau lebih cepat saat WS putus, turunkan.
# ============================================================================
import argparse
import base64
try:
    import fcntl
except ImportError:  # Termux/Linux selalu ada; jaga-jaga saja
    fcntl = None
import gzip
import hashlib
import http.client
import json
import os
import queue
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

BASE = "https://www.folester.xyz"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
COOKIE_FILE = os.path.expanduser("~/.folester_session_cookies.txt")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")

# ---------------------------------------------------------------------------
# Ed25519 murni-Python (RFC 8032, tanpa library tambahan) + Base58
# Dipakai cuma untuk menandatangani pesan login Folester di HP kamu sendiri.
# ---------------------------------------------------------------------------
_NBITS = 256
_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _Q - 2, _Q) % _Q
_I = pow(2, (_Q - 1) // 4, _Q)


def _H(m):
    return hashlib.sha512(m).digest()


def _inv(x):
    return pow(x, _Q - 2, _Q)


def _xrecover(y):
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = pow(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_By = 4 * _inv(5) % _Q
_Bx = _xrecover(_By)
_BASE = [_Bx % _Q, _By]


def _edwards(P, Q):
    x1, y1 = P
    x2, y2 = Q
    denom = _inv(1 + _D * x1 * x2 * y1 * y2)
    x3 = (x1 * y2 + x2 * y1) * denom % _Q
    denom2 = _inv(1 - _D * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * denom2 % _Q  # + karena kurva Ed25519 a=-1
    return [x3, y3]


def _scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q


def _encodeint(y):
    bits = [(y >> i) & 1 for i in range(_NBITS)]
    return bytes([sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(_NBITS // 8)])


def _encodepoint(P):
    x, y = P
    bits = [(y >> i) & 1 for i in range(_NBITS - 1)] + [x & 1]
    return bytes([sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(_NBITS // 8)])


def _bit(h, i):
    return (h[i // 8] >> (i % 8)) & 1


def _Hint(m):
    h = _H(m)
    return sum(2 ** i * _bit(h, i) for i in range(2 * _NBITS))


def ed25519_publickey(seed32):
    h = _H(seed32)
    a = 2 ** 254 + sum(2 ** i * _bit(h, i) for i in range(3, 254))
    A = _scalarmult(_BASE, a)
    return _encodepoint(A)


def ed25519_sign(msg, seed32, pubkey32):
    h = _H(seed32)
    a = 2 ** 254 + sum(2 ** i * _bit(h, i) for i in range(3, 254))
    r = _Hint(h[32:] + msg)
    R = _scalarmult(_BASE, r)
    S = (r + _Hint(_encodepoint(R) + pubkey32 + msg) * a) % _L
    return _encodepoint(R) + _encodeint(S)


_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(b):
    n = int.from_bytes(b, "big")
    s = ""
    while n > 0:
        n, r = divmod(n, 58)
        s = _B58[r] + s
    pad = 0
    for c in b:
        if c == 0:
            pad += 1
        else:
            break
    return "1" * pad + s


def base58_decode(s):
    n = 0
    for c in s:
        n = n * 58 + _B58.index(c)
    b = n.to_bytes((n.bit_length() + 7) // 8, "big") if n > 0 else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + b


# ---------------------------------------------------------------------------
# HTTP (JSON) — Python murni dulu, curl sebagai cadangan
# Dulu urllib kena HTTP 403 dari Folester, jadi semua request lewat curl.
# Sekarang HTTP bawaan Python (http.client + UA browser) bisa membaca API
# Folester dengan lengkap (terverifikasi live 2026-11-15: daftar 1.289 Frame
# ~1 MB + nonce + /me). urllib.request masih bermasalah (balasan besar
# terpotong di tengah jalan), jadi yang dipakai http.client langsung.
# Kalau jalur Python gagal (apa pun alasannya), otomatis dicoba lewat curl
# (kalau curl terpasang). Jadi di Termux cukup `pkg install python`.
# ---------------------------------------------------------------------------
# log() dipanggil dari thread utama dan thread websocket, jadi tulis log
# dikunci supaya barisnya tidak tercampur.
_LOG_LOCK = threading.Lock()


_LOG_F = None


def _log_open():
    """Handle file log persisten (MAX PATCH): dulu tiap log() membuka +
    menutup bot.log (open/write/close) — beberapa milidetik per baris,
    termasuk baris 'retry BUY' yang ditulis TEPAT SEBELUM trade dikirim.
    Sekarang file dibuka sekali dan dipakai ulang (flush tiap baris, jadi
    tidak ada yang hilang kalau bot mati). Kalau file dihapus di tengah
    jalan, handle dibuka ulang. Gagal buka = None (caller pakai cara lama)."""
    global _LOG_F
    try:
        if _LOG_F is None or _LOG_F.closed or not os.path.exists(LOG_FILE):
            try:
                if _LOG_F is not None:
                    _LOG_F.close()
            except Exception:
                pass
            _LOG_F = open(LOG_FILE, "a")
    except OSError:
        _LOG_F = None
    return _LOG_F


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
        try:
            f = _log_open()
            if f is None:
                raise OSError("log tidak bisa dibuka")
            f.write(line + "\n")
            f.flush()
        except OSError:
            try:
                with open(LOG_FILE, "a") as f:
                    f.write(line + "\n")
            except OSError:
                pass


# Berapa kali request dicoba ulang kalau jaringannya gagal sesaat (DNS, putus,
# timeout, server 5xx). Bukan untuk error 4xx (login salah, tidak lolos
# syarat, dsb.) — itu langsung gagal supaya tidak buang waktu.
RETRY_ATTEMPTS = 5
RETRYABLE_CURL_RC = {6, 7, 28, 35, 47, 52, 56}
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


# Berapa kali request dicoba ulang kalau jaringannya gagal sesaat (DNS,
# putus, timeout, server 5xx). Bukan untuk error 4xx (login salah, tidak
# lolos syarat, dsb.) — itu langsung gagal supaya tidak buang waktu.
RETRY_ATTEMPTS = 5
RETRYABLE_CURL_RC = {6, 7, 28, 35, 47, 52, 56}
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


class _RetryableError(RuntimeError):
    """Gagal sesaat (jaringan / server sibuk): boleh coba backend lain atau
    coba lagi. Error lain (4xx, JSON rusak) langsung fatal."""


def _read_cookies():
    """Baca cookie sesi dari file (format Netscape, sama seperti yang curl
    tulis) -> dict nama: nilai. Dipakai jalur Python supaya sesi login
    yang dibuat curl (atau sebaliknya) tetap kebaca."""
    cookies = {}
    try:
        with open(COOKIE_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
    except OSError:
        pass
    return cookies


def _write_cookies(cookies):
    """Tulis cookie ke file format Netscape supaya curl juga bisa baca."""
    try:
        with open(COOKIE_FILE, "w") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for name, value in cookies.items():
                f.write(f".folester.xyz\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
        os.chmod(COOKIE_FILE, 0o600)
    except OSError:
        pass


# KEEP-ALIVE PATCH 23 Nov 2026 (Berly: "buatkan keep-alive patch"):
# Versi lama membuka TCP + TLS baru di SETIAP request lalu menutupnya —
# tiap retry beli di jendela 30-35 dtk membayar handshake TLS lagi
# (~100 ms+ di HP). Sekarang satu koneksi HTTPS dipakai ulang untuk
# semua request ke host yang sama. Kalau server sudah menutup koneksi
# yang menganggur (idle), percobaan pertama gagal lalu otomatis
# disambung ulang sekali dengan koneksi baru di dalam panggilan yang
# sama — paling buruk sama cepatnya dengan versi lama, tidak lebih
# lambat. Koneksi TIDAK dipakai ulang kalau server bilang Connection:
# close. Hanya dipakai dari thread utama (WS punya soket sendiri).
_KA_CONN = {}  # (host, port) -> HTTPSConnection yang masih hidup
_KA_LOCK = threading.Lock()
_KA_STATS = {"fresh": 0, "reused": 0, "reconnect": 0}


def _ka_drop(host, port):
    """Buang koneksi keep-alive yang sudah mati / ditutup server."""
    conn = _KA_CONN.pop((host, port), None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


def _ka_fresh_conn(host, port):
    """Buka koneksi HTTPS baru dan simpan untuk dipakai ulang."""
    raw = _raw_connect(host, port)
    ctx = ssl.create_default_context()
    ss = ctx.wrap_socket(raw, server_hostname=host)
    ss.settimeout(20)
    conn = http.client.HTTPSConnection(host, port, timeout=20)
    conn.sock = ss
    _KA_CONN[(host, port)] = conn
    _KA_STATS["fresh"] += 1
    return conn


def _py_json(url, method="GET", data=None, use_cookies=False):
    """Satu request JSON lewat http.client (Python murni), koneksi
    keep-alive dipakai ulang kalau masih hidup."""
    u = urlparse(url)
    host, port = u.hostname, u.port or 443
    path = u.path or "/"
    if u.query:
        path += "?" + u.query
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Accept-Encoding": "gzip", "Connection": "keep-alive"}
    body = None
    if method == "POST":
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode() if data is not None else b"{}"
    cookies = _read_cookies() if use_cookies else {}
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    with _KA_LOCK:
        for _attempt in range(2):  # ke-2 hanya kalau koneksi lama mati
            conn = _KA_CONN.get((host, port))
            if conn is not None:
                try:
                    if conn.sock is None or conn.sock.fileno() == -1:
                        raise OSError("koneksi keep-alive sudah tertutup")
                except OSError:
                    _ka_drop(host, port)
                    conn = None
            if conn is None:
                try:
                    conn = _ka_fresh_conn(host, port)
                except (OSError, socket.timeout, ssl.SSLError,
                        http.client.HTTPException) as e:
                    raise _RetryableError(f"http {method} {url} gagal: {e}")
            else:
                _KA_STATS["reused"] += 1
            try:
                conn.request(method, path, body=body, headers=headers)
                resp = conn.getresponse()
                raw_body = resp.read()
                if resp.getheader("Content-Encoding") == "gzip":
                    try:
                        raw_body = gzip.decompress(raw_body)
                    except (OSError, EOFError) as e:
                        raise _RetryableError(
                            f"http {method} {url} gagal dekompresi gzip: {e}")
                if use_cookies:
                    new = {}
                    for k, v in resp.getheaders():
                        if k.lower() == "set-cookie":
                            pair = v.split(";", 1)[0]
                            if "=" in pair:
                                name, val = pair.split("=", 1)
                                new[name.strip()] = val.strip()
                    if new:
                        cookies.update(new)
                        _write_cookies(cookies)
                code = resp.status
                # Server menutup koneksi sesudah balasan ini: jangan
                # pakai ulang, buang supaya request berikut buka baru.
                try:
                    if resp.will_close:
                        _ka_drop(host, port)
                except Exception:
                    pass
                break
            except (OSError, socket.timeout, ssl.SSLError,
                    http.client.HTTPException) as e:
                _ka_drop(host, port)
                if _attempt == 0:
                    _KA_STATS["reconnect"] += 1
                    continue
                raise _RetryableError(f"http {method} {url} gagal: {e}")
    if code >= 400:
        try:
            err = json.loads(raw_body)
            detail = err.get("error") or err
        except (json.JSONDecodeError, AttributeError):
            detail = raw_body[:200].decode(errors="replace")
        msg = f"HTTP {code} dari {url}: {detail}"
        if code in RETRYABLE_HTTP:
            raise _RetryableError(msg)
        raise RuntimeError(msg)
    try:
        return json.loads(raw_body)
    except json.JSONDecodeError:
        raise RuntimeError(f"balasan bukan JSON dari {url}: {raw_body[:200]!r}")


def _curl_json(url, method="GET", data=None, use_cookies=False):
    """Satu request JSON lewat curl (cadangan kalau jalur Python gagal)."""
    cmd = ["curl", "-s", "--compressed", "--max-time", "20", "-A", UA, "-w", "\n%{http_code}"]
    if use_cookies:
        cmd += ["-b", COOKIE_FILE, "-c", COOKIE_FILE]
    if method == "POST":
        cmd += ["-X", "POST", "-H", "content-type: application/json"]
        if data is not None:
            cmd += ["-d", json.dumps(data)]
    cmd.append(url)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        raise _RetryableError(f"curl {method} {url} timeout (>30 dtk)")
    except OSError as e:
        raise _RetryableError(f"curl {method} {url} gagal dijalankan: {e}")
    if out.returncode != 0:
        msg = f"curl {method} {url} gagal rc={out.returncode}: {out.stderr.strip()[:200]}"
        if out.returncode in RETRYABLE_CURL_RC:
            raise _RetryableError(msg)
        raise RuntimeError(msg)
    body, _, status = out.stdout.rpartition("\n")
    try:
        code = int(status.strip())
    except ValueError:
        code = 0
    if code >= 400:
        try:
            err = json.loads(body)
            detail = err.get("error") or err
        except (json.JSONDecodeError, AttributeError):
            detail = body[:200]
        msg = f"HTTP {code} dari {url}: {detail}"
        if code in RETRYABLE_HTTP:
            raise _RetryableError(msg)
        raise RuntimeError(msg)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"balasan bukan JSON dari {url}: {body[:200]}")


def http_json(url, method="GET", data=None, use_cookies=False, fast=False, curl_only=False):
    """Request JSON: coba Python murni dulu, kalau gagal coba curl.
    Gagal sesaat dicoba ulang (5x, jeda 1/2/4/8 dtk); error 4xx (login salah,
    tidak lolos syarat, dsb.) langsung gagal supaya tidak buang waktu.
    fast=True (SPEED-2, khusus trade): cuma 2 percobaan tanpa jeda tidur —
    kalau gagal sesaat, biarkan loop burst 0,2 dtk yang mencoba ulang,
    bukan tidur 1/2/4/8 dtk di dalam sini. curl_only=True (SPEED-2, khusus
    polling): cuma lewat curl, supaya fetch daftar Frame 1 MB tidak memegang
    _KA_LOCK dan memblokir trade di koneksi keep-alive."""
    last_err = RuntimeError(f"http {method} {url} gagal tanpa balasan")
    backends = (_curl_json,) if curl_only else (_py_json, _curl_json)
    attempts = 2 if fast else RETRY_ATTEMPTS
    for attempt in range(1, attempts + 1):
        for backend in backends:
            try:
                return backend(url, method, data, use_cookies)
            except _RetryableError as e:
                last_err = e
                continue
        if attempt < attempts:
            wait = 0 if fast else 2 ** (attempt - 1)
            if wait:
                log(f"jaringan gagal ({last_err}), coba lagi {attempt + 1}/{attempts} setelah {wait} dtk")
                time.sleep(wait)
    raise last_err


# ---------------------------------------------------------------------------
# WebSocket live feed /api/live (pure stdlib, tanpa library tambahan)
# Jalur UTAMA deteksi Frame baru. Server mengirim tiap trade dan tiap update
# harga sebagai JSON; trade pertama sebuah Frame baru mendarat ~1 detik
# setelah Frame dibuat (terverifikasi live 2026-11-15, 240 dtk, 260 pesan,
# 0 putus). Pesan yang dipakai cuma tradeUpdate / priceUpdate — keduanya
# membawa objek frame lengkap (id, name, price, trades, created_at).
# Koneksi ini cuma BACA (tanpa login, tanpa sign). Kalau putus, thread ini
# menyambung lagi sendiri (backoff 1-30 dtk); sementara itu polling tetap
# jalan, jadi tidak ada jeda deteksi.
# ---------------------------------------------------------------------------
WS_HOST = "www.folester.xyz"
WS_PORT = 443
WS_PATH = "/api/live"
_WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _nodelay(s):
    """Matikan algoritma Nagle di soket ini (SPEED-4): request kecil (POST
    trade ~300 byte) dikirim http.client dalam 2x send (header lalu body);
    tanpa TCP_NODELAY, send kedua bisa tertahan sampai ~40 ms menunggu ACK
    send pertama. Efeknya cuma beberapa milidetik, tapi di balapan detik 30
    tiap milidetik dihitung. Gagal set = abaikan, bukan error."""
    try:
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except (OSError, AttributeError):
        pass


def _raw_connect(host, port):
    """Koneksi TCP. Coba langsung dulu; kalau gagal dan ada proxy di env
    (VM Muse), lewat CONNECT proxy itu. Di Termux tidak ada proxy env,
    jadi selalu langsung. Kredensial proxy dibaca dari env saat jalan,
    tidak pernah dicetak atau disimpan."""
    try:
        s = socket.create_connection((host, port), timeout=15)
        _nodelay(s)
        return s
    except (OSError, socket.timeout) as first_err:
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        if not proxy:
            raise first_err
        u = urlparse(proxy)
        if not u.hostname or u.hostname in ("localhost", "127.0.0.1"):
            raise first_err
        s = socket.create_connection((u.hostname, u.port or 3128), timeout=15)
        req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
        if u.username:
            auth = base64.b64encode(f"{u.username}:{u.password}".encode()).decode()
            req += f"Proxy-Authorization: Basic {auth}\r\n"
        req += "\r\n"
        s.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                s.close()
                raise RuntimeError("proxy menutup koneksi saat CONNECT")
            buf += chunk
        if b" 200 " not in buf.split(b"\r\n")[0]:
            s.close()
            raise RuntimeError("proxy CONNECT gagal")
        _nodelay(s)
        return s


def _ws_connect(host, port, path):
    raw = _raw_connect(host, port)
    use_tls = (port == 443)
    ss = raw
    if use_tls:
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(raw, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    host_hdr = host if port == 443 else f"{host}:{port}"
    origin = f"https://{host}" if use_tls else f"http://{host}"
    req = (f"GET {path} HTTP/1.1\r\nHost: {host_hdr}\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
           f"Origin: {origin}\r\nUser-Agent: {UA}\r\n\r\n")
    ss.sendall(req.encode())
    ss.settimeout(15)
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = ss.recv(4096)
        if not chunk:
            raise RuntimeError("websocket menutup koneksi saat handshake")
        buf += chunk
    head = buf.split(b"\r\n\r\n", 1)[0]
    if b"101" not in head.split(b"\r\n")[0]:
        raise RuntimeError(f"websocket handshake gagal: {head[:120]!r}")
    return ss, buf.split(b"\r\n\r\n", 1)[1]


def _ws_send(ss, opcode, payload=b""):
    mask = os.urandom(4)
    ln = len(payload)
    hdr = bytearray([0x80 | opcode])
    if ln < 126:
        hdr.append(0x80 | ln)
    elif ln < 65536:
        hdr.append(0x80 | 126)
        hdr += struct.pack(">H", ln)
    else:
        hdr.append(0x80 | 127)
        hdr += struct.pack(">Q", ln)
    hdr += mask
    ss.sendall(bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _ws_read_frame(ss, buf):
    """Baca satu frame websocket. Kembalikan (fin, opcode, payload, sisa buf)."""
    while len(buf) < 2:
        chunk = ss.recv(4096)
        if not chunk:
            raise RuntimeError("websocket ditutup server")
        buf += chunk
    b1, b2 = buf[0], buf[1]
    fin = b1 & 0x80
    opcode = b1 & 0x0F
    masked = b2 & 0x80
    ln = b2 & 0x7F
    i = 2
    if ln == 126:
        while len(buf) < i + 2:
            buf += ss.recv(4096)
        ln = struct.unpack(">H", buf[i:i + 2])[0]
        i += 2
    elif ln == 127:
        while len(buf) < i + 8:
            buf += ss.recv(4096)
        ln = struct.unpack(">Q", buf[i:i + 8])[0]
        i += 8
    if masked:
        while len(buf) < i + 4:
            buf += ss.recv(4096)
        mask = buf[i:i + 4]
        i += 4
    else:
        mask = None
    while len(buf) < i + ln:
        chunk = ss.recv(65536)
        if not chunk:
            raise RuntimeError("websocket ditutup server")
        buf += chunk
    payload = bytearray(buf[i:i + ln])
    if mask:
        for j in range(len(payload)):
            payload[j] ^= mask[j % 4]
    return fin, opcode, bytes(payload), buf[i + ln:]


def _ws_recv_text(ss, buf):
    """Baca satu pesan teks lengkap (gabungkan fragment, jawab ping).
    Kembalikan (bytes_pesan, sisa buf). Raise kalau koneksi ditutup."""
    fragments = bytearray()
    while True:
        fin, op, payload, buf = _ws_read_frame(ss, buf)
        if op == 9:  # ping -> pong
            _ws_send(ss, 10, payload)
            continue
        if op == 8:  # close
            raise RuntimeError("websocket ditutup server (close frame)")
        if op == 1 or op == 0:  # teks / lanjutan
            fragments += payload
            if fin:
                return bytes(fragments), buf
            continue
        # frame lain (biner dsb.): abaikan
        continue


def _ws_normalize_frame(fr):
    """Ubah objek frame dari pesan WS ke bentuk yang dipakai process_frame.
    Kembalikan None kalau field pentingnya tidak ada / tidak valid."""
    try:
        return {"id": str(fr["id"]), "name": str(fr.get("name", "?")),
                "price": float(fr.get("price", 0) or 0),
                "trades": int(fr.get("trades", 0) or 0),
                "created_at": str(fr.get("created_at", ""))}
    except (KeyError, TypeError, ValueError):
        return None


def ws_frames_from_message(msg):
    """Ambil objek frame kandidat dari satu pesan WS (tradeUpdate /
    priceUpdate / frame langsung). Pesan lain (tanpa frame) -> []."""
    out = []
    if not isinstance(msg, dict):
        return out
    for key in ("priceUpdate", "tradeUpdate"):
        u = msg.get(key)
        if isinstance(u, dict) and isinstance(u.get("frame"), dict):
            fr = _ws_normalize_frame(u["frame"])
            if fr:
                out.append(fr)
    if isinstance(msg.get("frame"), dict):
        fr = _ws_normalize_frame(msg["frame"])
        if fr:
            out.append(fr)
    return out


def ws_listen(frame_queue, status, stop_event):
    """Thread pendengar websocket: sambung, baca pesan, lempar frame ke queue.
    Putus -> sambung lagi (backoff 1-30 dtk). Tidak pernah mematikan bot."""
    backoff = 1.0
    while not stop_event.is_set():
        ss = None
        try:
            ss, buf = _ws_connect(WS_HOST, WS_PORT, WS_PATH)
            status["connected"] = True
            status["last_msg"] = time.monotonic()
            log("websocket live tersambung (deteksi Frame baru <1 dtk)")
            backoff = 1.0
            ss.settimeout(30)
            while not stop_event.is_set():
                text, buf = _ws_recv_text(ss, buf)
                status["last_msg"] = time.monotonic()
                try:
                    msg = json.loads(text)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                for fr in ws_frames_from_message(msg):
                    frame_queue.put(fr)
        except Exception as e:
            status["connected"] = False
            status["reconnects"] = status.get("reconnects", 0) + 1
            log(f"websocket putus ({e}), sambung lagi {backoff:.0f} dtk (polling tetap jalan)")
            if ss is not None:
                try:
                    ss.close()
                except Exception:
                    pass
            if stop_event.wait(backoff):
                break
            backoff = min(backoff * 2, 30)
        finally:
            status["connected"] = False


# ---------------------------------------------------------------------------
# Lock: satu proses bot per wallet (file lock + file PID)
# Kalau bot lama masih jalan (mis. `mulai` gagal mematikannya karena
# dijalankan pakai flag), bot baru MENOLAK jalan dan bilang begitu — jadi
# tidak ada dua bot yang beli dobel, rebutan cookie sesi, dan menguras
# saldo yang sama sampai negatif. Lock dilepas otomatis kalau proses mati.
# ---------------------------------------------------------------------------
_LOCK_FD = None


def acquire_lock(wallet):
    """Kunci bot untuk wallet ini. Kembalikan False kalau bot lain untuk
    wallet yang sama sudah jalan."""
    global _LOCK_FD
    path = os.path.expanduser(f"~/.folester-{wallet[:8]}.lock")
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    except OSError as e:
        log(f"lock gagal dibuka {path}: {e} (lanjut tanpa lock)")
        return True
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            print("BERHENTI: bot lain untuk wallet ini SUDAH JALAN.",
                  file=sys.stderr)
            print("Matikan dulu bot lamanya, baru jalankan lagi:",
                  file=sys.stderr)
            print("  pkill -f bot.py   (lalu cek: ps aux | grep bot.py)",
                  file=sys.stderr)
            print("Atau jalankan ulang lewat: mulai   (versi baru mematikan",
                  file=sys.stderr)
            print("bot lama dulu lewat file PID + cookie).", file=sys.stderr)
            return False
    _LOCK_FD = fd
    try:
        with open(COOKIE_FILE + ".pid", "w") as pf:
            pf.write(str(os.getpid()))
    except OSError:
        pass
    return True


# ---------------------------------------------------------------------------
# Wallet + login
# ---------------------------------------------------------------------------
def load_keypair(path):
    """Baca keypair dari file. Dua format diterima:
    1. File keypair Solana (JSON, mis. ~/.config/solana/id.json) — daftar 64 angka.
    2. File berisi SATU BARIS private key base58 (hasil export dari Phantom).
    File ini dibaca di HP kamu sendiri dan tidak pernah dikirim ke mana pun."""
    with open(path) as f:
        text = f.read().strip()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raw = None
    if raw is None:
        secret = base58_decode(text)
        if len(secret) not in (32, 64):
            raise ValueError("isi file bukan keypair JSON dan bukan private key base58 yang valid")
        raw = list(secret)
    if isinstance(raw, dict):
        raw = raw.get("keypair") or raw.get("secretKey") or raw.get("secret_key")
    secret = bytes(raw)
    if len(secret) == 64:
        seed, pubkey = secret[:32], secret[32:]
    elif len(secret) == 32:
        seed = secret
        pubkey = ed25519_publickey(seed)
    else:
        raise ValueError("format keypair tidak dikenal (harus 32 atau 64 byte)")
    # Pastikan pubkey hasil turunan cocok dengan 32 byte terakhir (kalau ada).
    if len(secret) == 64 and ed25519_publickey(seed) != pubkey:
        raise ValueError("keypair tidak konsisten (seed dan pubkey tidak cocok)")
    return seed, pubkey, base58_encode(pubkey)


def sign_in(wallet, seed):
    """Minta nonce, tanda tangani pesan login, verifikasi. Kembalikan True kalau OK."""
    d = http_json(f"{BASE}/api/auth/nonce", method="POST", data={"wallet": wallet})
    nonce, message = d.get("nonce"), d.get("message", "")
    if not nonce or not message:
        raise RuntimeError(f"nonce tidak didapat: {d}")
    # SAFETY: cuma tandatangani pesan login Folester, bukan yang lain.
    if not message.startswith("folester.xyz wants you to sign in"):
        raise RuntimeError(f"pesan login tidak dikenal, BERHENTI: {message[:120]}")
    if wallet not in message or nonce not in message:
        raise RuntimeError("pesan login tidak menyebut wallet/nonce ini, BERHENTI")
    sig = ed25519_sign(message.encode(), seed, ed25519_publickey(seed))
    sig_b64 = base64.b64encode(sig).decode()
    r = http_json(f"{BASE}/api/auth/verify", method="POST",
                  data={"wallet": wallet, "nonce": nonce, "message": message,
                        "signature": sig_b64}, use_cookies=True)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"verify gagal: {r}")
    log(f"login OK wallet={wallet[:4]}...{wallet[-4:]}")
    return True


def get_me(wallet):
    return http_json(f"{BASE}/api/play/me?wallet={wallet}", use_cookies=True)


def ensure_joined(wallet):
    me = get_me(wallet)
    player = me.get("player")
    if player:
        gate = me.get("gate") or {}
        checks = gate.get("checks") or []
        log(f"gate: lolos {gate.get('passed')}/{4} " +
            ", ".join(f"{c['key']}={'OK' if c.get('ok') else 'FAIL'}({c.get('have')}/{c.get('need')})"
                      for c in checks))
        log(f"saldo ANUL={player.get('balance'):.2f} poin={player.get('points')} "
            f"rank={player.get('rank')} banned={player.get('banned')}")
        if player.get("banned"):
            raise RuntimeError("wallet ini BANNED di Folester, berhenti")
        return player
    # Belum terdaftar: situs menghitung gate lewat /api/scan dulu, baru /join.
    log("belum terdaftar sebagai pemain, menjalankan scan kelayakan...")
    for i in range(40):
        s = http_json(f"{BASE}/api/scan", method="POST", data={}, use_cookies=True)
        if isinstance(s, dict) and s.get("status") in ("done", "registered"):
            break
        if isinstance(s, dict) and s.get("error"):
            raise RuntimeError(f"scan gagal: {s}")
        time.sleep(0.4 if isinstance(s, dict) and s.get("status") == "scanning" else 2)
    me = get_me(wallet)
    gate = me.get("gate") or {}
    checks = gate.get("checks") or []
    if checks:
        log(f"gate: lolos {gate.get('passed')}/{4} " +
            ", ".join(f"{c['key']}={'OK' if c.get('ok') else 'FAIL'}({c.get('have')}/{c.get('need')})"
                      for c in checks))
    log("mencoba join...")
    r = http_json(f"{BASE}/api/play/join", method="POST", data={}, use_cookies=True)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"join gagal: {r} — wallet ini tidak lolos syarat Folester")
    me = get_me(wallet)
    player = me.get("player")
    if not player:
        raise RuntimeError(f"join tidak menghasilkan pemain: {me}")
    log(f"join OK, saldo ANUL={player.get('balance'):.2f}")
    return player


# ---------------------------------------------------------------------------
# Pantau + beli
# ---------------------------------------------------------------------------
def fetch_frames():
    # SPEED-2: polling HANYA lewat curl — fetch 1 MB ini tidak boleh
    # memegang _KA_LOCK / koneksi keep-alive yang dipakai trade.
    d = http_json(f"{BASE}/api/play/frames?sort=created_at&q=", curl_only=True)
    frames = sorted(d.get("frames", []), key=lambda f: f["created_at"])
    return frames


# Jeda antar trade yang dipaksakan server Folester: 2 detik. Kalau kena
# trade_cooldown, bot menunggu sedikit lebih lama (2,1 dtk) sebelum coba lagi.
TRADE_COOLDOWN_RETRY = 2.1
# Server Folester baru membuka trading 30 dtk setelah Frame dibuat (dari
# kode situsnya; Opensea ditolak launch_wait bahkan di umur 20 dtk).
# Retry launch_wait pertama dijadwalkan ke umur ini, bukan tiap 0,5 dtk.
LAUNCH_OPEN_AGE = 30.0
# SPEED PATCH 23 Nov 2026 (Berly: "secepat kilat"): jendela balapan yang
# sebenarnya adalah umur 30-35 dtk, BUKAN sejak launch. Spam tiap 0,001 dtk
# mustahil (1 request HTTP saja 50-200+ ms, server cooldown 2 dtk, dan
# 1000 req/dtk = rate-limit + risiko ban Terms §11). Jadi: coba pertama
# TEPAT umur 30,0 dtk, lalu burst retry tiap 0,2 dtk sampai umur 35 dtk,
# baru melambat ke 0,5 dtk. Itu ~26 percobaan di jendela buka, vs 1x di
# versi lama (30,5 dtk sekali).
# MAX PATCH 24 Nov 2026 (Berly: "paling cepat sampai batas maksimum"):
# burst 0,2 -> 0,1 dtk (~50 percobaan di jendela 30-35 dtk). Hanya jalan
# kalau percobaan pertama masih launch_wait; kalau sudah berhasil beli,
# burst berhenti. Risiko: server bisa rate-limit kalau kebanyakan request
# — error rate_limited sudah ditangani sebagai 'retryable' (antre ulang).
OPEN_BURST_END = 35.0
OPEN_BURST_RETRY = 0.1
# Error trade yang sifatnya sementara: antre ulang, jangan buang Frame-nya.
RETRYABLE_TRADE_ERRORS = {
    "rate_limited", "too_many_requests", "server_busy", "try_again_later",
    "temporarily_unavailable", "insufficient_balance", "frame_not_found",
}
# Kalau posisi terkunci semua saat mau auto-sell, coba lagi tiap 5 dtk...
SELL_LOCK_RETRY = 5.0
# ...sampai 300 dtk sesudah jadwal jual; kalau tetap gagal, posisi ditahan.
SELL_MAX_WAIT = 300


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _balance_from_me(me, fallback):
    """Ambil saldo dari /me. Pakai cek `is not None`, BUKAN `or`: saldo 0
    itu nilai yang sah — kalau pakai `or`, 0 dianggap tidak ada dan bot
    memakai saldo lama dikurangi amount (salah, bisa negatif)."""
    player = (me or {}).get("player") or {}
    bal = player.get("balance")
    return float(bal) if bal is not None else fallback


def _launch_wait_delay(created, now):
    """Jeda sampai trading dibuka (umur 30,0 dtk tepat), lalu burst
    0,2 dtk selama jendela buka (umur 30-35 dtk), baru 0,5 dtk sesudahnya.
    Jam HP vs server bisa meleset sedikit — burst 0,2 dtk menutup itu."""
    age = (now - created).total_seconds()
    if age < LAUNCH_OPEN_AGE:
        return max(0.0, LAUNCH_OPEN_AGE - age)
    if age < OPEN_BURST_END:
        return OPEN_BURST_RETRY
    return 0.5


def _not_first_reason(latest, fid, initial):
    """Alasan SKIP kalau bot sudah bukan pembeli pertama (SKIP-IF-NOT-FIRST
    PATCH): data Frame terbaru (dari WS/poll) menunjukkan sudah ada yang
    beli duluan — harga sudah naik dan pembeli pertama itulah yang akan
    menjual ke kita (pola MOONBEAM 24 Nov: FNrw beli 200 ANUL, jual
    370 ANUL setelah bot beli). Kembalikan None kalau masih aman dibeli.
    `latest` = dict frame_id -> objek Frame terbaru; `initial` = objek
    Frame saat pertama terdeteksi (harga awal, trades=0)."""
    fresh = latest.get(fid)
    if fresh is None or fresh is initial:
        return None
    trades = _num(fresh.get("trades", 0))
    price = _num(fresh.get("price", 0))
    start = _num(initial.get("price", 0))
    if trades > 0:
        return f"sudah ada {trades:g} trade, harga {price:.6f}"
    if start > 0 and price > start * 1.5:
        return f"harga naik {price / start:.1f}x dari {start:.6f} ke {price:.6f}"
    return None


def _server_time_offset():
    """Selisih jam server Folester vs jam HP (detik; >0 = jam HP tertinggal).
    Diukur sekali saat start dari header Date balasan HEAD https://folester.xyz.
    Umur Frame dihitung dari created_at server, jadi jam HP yang meleset 1 dtk
    membuat tembakan umur 30,0 dtk mendarat di umur server 31 dtk — kalah
    start. Gagal ukur / selisih >5 menit = 0 (jangan pakai angka mencurigakan)."""
    try:
        out = subprocess.run(["curl", "-s", "-I", "--max-time", "10", BASE],
                             capture_output=True, text=True, timeout=15)
        for line in out.stdout.splitlines():
            if line.lower().startswith("date:"):
                srv = parsedate_to_datetime(line[5:].strip())
                off = srv.timestamp() - time.time()
                return off if abs(off) <= 300 else 0.0
    except Exception:
        pass
    return 0.0


def _log_pause(state, reason):
    """Catat alasan jeda beli, paling sering 60 dtk sekali supaya log
    tidak banjir — bot tetap hidup dan memantau."""
    state["paused_reason"] = reason
    now_t = time.monotonic()
    if now_t - state.get("last_pause_log", 0) >= 60:
        state["last_pause_log"] = now_t
        log(f"JEDA BELI: {reason} — bot tetap memantau, beli lanjut otomatis "
            f"kalau saldo/batas pulih (ubah di python3 atur.py kalau mau)")


def _limits_reason(buys, spent, balance, a):
    """Alasan kenapa bot belum boleh beli sekarang (None kalau boleh)."""
    if buys >= a.max_buys:
        return f"max_buys tercapai ({buys}/{a.max_buys})"
    if spent + a.amount > a.budget:
        return f"budget tercapai (terpakai {spent:.0f}/{a.budget:.0f} ANUL)"
    if balance - a.amount < a.reserve:
        return (f"saldo {balance:.2f} ANUL di bawah reserve+amount "
                f"({a.reserve:g}+{a.amount:g}) — jual posisi manual dulu "
                f"sampai saldo pulih")
    return None


def _do_trade(frame, side, amount, wallet, seed, state):
    """Satu percobaan trade (buy/sell). Kembalikan (status, hasil, lock):
    'ok' = berhasil; 'launch_wait' / 'trade_cooldown' / 'retryable' = coba
    lagi nanti; 'position_locked' = sebagian/seluruh posisi terkunci (lock
    berisi available_qty dsb.); 'fail' = gagal lain (jangan coba lagi)."""
    body = {"frameId": frame["id"], "side": side, "amount": amount}
    tag = side.upper()
    # Reauth BOLEH tiap percobaan trade (bukan sekali seumur hidup bot):
    # sesi bisa habis berkali-kali dalam run berjam-jam. Dibatasi 1x per
    # percobaan oleh loop range(2) di bawah, jadi tidak bisa loop selamanya.
    reauth_tried = False
    for _attempt in range(2):  # percobaan ke-2 hanya sesudah login ulang
        try:
            # SPEED-2: fast=True — gagal sesaat langsung kembali sebagai
            # 'retryable' supaya loop burst 0,2 dtk yang mencoba ulang,
            # bukan tidur 1/2/4/8 dtk di dalam http_json.
            r = http_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True, fast=True)
        except RuntimeError as e:
            msg = str(e)
            if "launch_wait" in msg:
                log(f"{tag} {frame['name']} masih launch_wait, coba lagi nanti")
                return "launch_wait", None, None
            if "trade_cooldown" in msg:
                log(f"{tag} {frame['name']} kena trade_cooldown, coba lagi nanti")
                return "trade_cooldown", None, None
            if "sign_in_required" in msg and not reauth_tried:
                log("sesi habis, login ulang...")
                sign_in(wallet, seed)
                reauth_tried = True
                continue
            # 4xx yang jelas (bukan 429/408) = penolakan permanen server.
            # Selain itu (jaringan putus, 5xx sesudah 5x retry http_json,
            # timeout) = sementara, antre ulang saja.
            if "HTTP 4" in msg and "429" not in msg and "408" not in msg:
                log(f"{tag} {frame['name']} gagal HTTP: {e}")
                state["last_buy_error"] = msg[:120]
                state["last_buy_error_at"] = time.monotonic()
                return "fail", None, None
            log(f"{tag} {frame['name']} gagal sesaat ({e}), antre ulang")
            state["last_buy_error"] = msg[:120]
            state["last_buy_error_at"] = time.monotonic()
            return "retryable", None, None
        if isinstance(r, dict) and r.get("error"):
            err = r.get("error")
            if err == "launch_wait":
                log(f"{tag} {frame['name']} masih launch_wait, coba lagi nanti")
                return "launch_wait", None, None
            if err == "trade_cooldown":
                log(f"{tag} {frame['name']} kena trade_cooldown, coba lagi nanti")
                return "trade_cooldown", None, None
            if err == "position_locked":
                return "position_locked", None, r.get("lock") or {}
            if err == "sign_in_required" and not reauth_tried:
                log("sesi habis, login ulang...")
                sign_in(wallet, seed)
                reauth_tried = True
                continue
            if err in RETRYABLE_TRADE_ERRORS:
                log(f"{tag} {frame['name']} ditolak sementara ({err}), antre ulang")
                state["last_buy_error"] = str(err)[:120]
                state["last_buy_error_at"] = time.monotonic()
                return "retryable", None, None
            log(f"{tag} {frame['name']} ditolak: {r}")
            state["last_buy_error"] = str(r)[:120]
            state["last_buy_error_at"] = time.monotonic()
            return "fail", None, None
        return "ok", r, None
    log(f"{tag} {frame['name']} gagal: sesi habis sesudah login ulang")
    state["last_buy_error"] = "sesi habis sesudah login ulang"
    state["last_buy_error_at"] = time.monotonic()
    return "fail", None, None


def buy(frame, amount, wallet, seed, state):
    """Satu percobaan beli. Kembalikan (status, hasil) — lihat _do_trade."""
    status, r, _lock = _do_trade(frame, "buy", amount, wallet, seed, state)
    if status == "ok":
        log(f"BUY {frame['name']} amount={amount} ANUL -> dapat {r.get('base')} token, "
            f"harga {r.get('quote')} ANUL, fee {r.get('fee')}")
    return status, r


def sell(frame, amount_tokens, wallet, seed, state):
    """Satu percobaan jual (amount dalam TOKEN). Kembalikan
    (status, hasil, lock) — lihat _do_trade."""
    status, r, lock = _do_trade(frame, "sell", amount_tokens, wallet, seed, state)
    if status == "ok":
        realized = r.get("realized")
        pl = ""
        if realized is not None:
            try:
                pl = f", {'Profit' if float(realized) >= 0 else 'Loss'} {abs(float(realized)):.2f}"
            except (TypeError, ValueError):
                pl = ""
        log(f"SELL {frame['name']} {r.get('base')} token -> dapat "
            f"{_num(r.get('quote')) - _num(r.get('fee')):.2f} ANUL (fee {r.get('fee')}){pl}")
    return status, r, lock


# Pengaturan default. Nilai-nilai ini dipakai kalau tidak ada di config.json
# dan tidak disebut di perintah. config.json dibuat lewat `python3 atur.py`.
DEFAULTS = {
    "keypair": None,
    "amount": 100.0,
    "interval": 30.0,
    "heartbeat": 3.0,
    "no_ws": False,
    "max_buys": 50,
    "budget": 1000000000.0,
    "reserve": 100.0,
    "max_age": 120,
    "buy_delay": 0.5,
    "launch_wait_retry": 0.5,
    "auto_sell_delay": 0.0,
    "cookies": None,
    "once": False,
    "check_only": False,
}


def _load_config():
    """Baca pengaturan dari config.json di folder yang sama dengan bot.py.
    Kalau tidak ada atau rusak, kembalikan {} (pakai default). Isi file
    boleh sebagian saja — yang tidak ada diisi default."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(path) as f:
            cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def _resolve_args(a, cfg):
    """Isi argumen yang tidak disebut di perintah dari config.json, lalu
    dari default. Perintah selalu menang atas config.json."""
    for k, d in DEFAULTS.items():
        if getattr(a, k, None) is None:
            v = cfg.get(k, d)
            # config.json yang diedit manual bisa berisi "0,5" (string koma)
            # — ubah ke angka hanya untuk pengaturan numerik, bukan path.
            if isinstance(v, str) and isinstance(d, (int, float)):
                v = v.replace(",", ".")
                try:
                    v = float(v) if isinstance(d, float) else int(float(v))
                except (TypeError, ValueError):
                    v = d
            setattr(a, k, v)
    return a


def _angka(s):
    """float yang terima koma desimal Indonesia (0,5) maupun titik (0.5)."""
    return float(str(s).replace(",", "."))


def _bilangan_bulat(s):
    """int yang terima koma desimal Indonesia (mis. 50,0 -> 50)."""
    return int(float(str(s).replace(",", ".")))


def main():
    ap = argparse.ArgumentParser(description="Folester testnet auto-buy (Termux)")
    ap.add_argument("--keypair", default=None, help="path file keypair Solana, mis. ~/bacj-key.txt (atau isi di config.json lewat python3 atur.py)")
    ap.add_argument("--amount", type=_angka, default=None, help="ANUL per Frame baru (min 1)")
    ap.add_argument("--interval", type=_angka, default=None, help="detik antar cek polling cadangan (deteksi cepat lewat websocket; polling cuma cadangan kalau WS putus)")
    ap.add_argument("--heartbeat", type=_angka, default=None, help="detik antar kabar berkala di log (0 = mati)")
    ap.add_argument("--no-ws", action="store_true", default=None, help="matikan websocket, cuma pakai polling")
    ap.add_argument("--max-buys", type=_bilangan_bulat, default=None, help="berhenti setelah sekian beli")
    ap.add_argument("--budget", type=_angka, default=None, help="total ANUL maksimal yang dibelanjakan")
    ap.add_argument("--reserve", type=_angka, default=None, help="berhenti kalau saldo < ini")
    ap.add_argument("--max-age", type=_bilangan_bulat, default=None, help="cuma beli Frame umur <= sekian detik")
    ap.add_argument("--buy-delay", type=_angka, default=None, help="beli saat Frame berumur sekian detik setelah launch")
    ap.add_argument("--launch-wait-retry", type=_angka, default=None, help="jeda detik antar coba ulang saat server bilang launch_wait")
    ap.add_argument("--auto-sell-delay", type=_angka, default=None, help="jual otomatis sekian detik setelah beli (0 = mati)")
    ap.add_argument("--cookies", default=None, help="file cookie sesi (default ~/.folester_session_cookies.txt; wajib beda tiap akun kalau jalan 2 bot sekaligus)")
    ap.add_argument("--once", action="store_true", default=None, help="cek sekali lalu keluar")
    ap.add_argument("--check-only", action="store_true", default=None, help="cuma login + cek saldo, tanpa beli")
    a = ap.parse_args()
    _resolve_args(a, _load_config())
    if not a.keypair:
        ap.error("--keypair belum diisi. Jalankan python3 atur.py dulu, atau: python3 bot.py --keypair ~/bacj-key.txt")
    if "/" not in a.keypair and len(a.keypair) > 40:
        print("BERHENTI: --keypair harus path file, bukan private key langsung.", file=sys.stderr)
        print("Simpan dulu key-nya ke file, mis. cat > ~/bacj-key.txt (tempel key, Enter, Ctrl+D),", file=sys.stderr)
        print("lalu jalankan bot dengan path file itu.", file=sys.stderr)
        return 2
    global COOKIE_FILE
    if a.cookies:
        COOKIE_FILE = os.path.expanduser(a.cookies)
    if a.amount < 1:
        print("amount minimal 1 ANUL", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(COOKIE_FILE) or ".", exist_ok=True)
    try:
        os.chmod(COOKIE_FILE, 0o600)
    except OSError:
        pass

    try:
        seed, pubkey, wallet = load_keypair(os.path.expanduser(a.keypair))
    except FileNotFoundError:
        print(f"BERHENTI: file keypair tidak ditemukan: {os.path.expanduser(a.keypair)}", file=sys.stderr)
        print("File itu belum ada di Termux. Export private key dari Phantom (wallet BacJ),", file=sys.stderr)
        print("simpan ke satu file di Termux, lalu ulangi dengan --keypair <file itu>.", file=sys.stderr)
        print("Jangan kirim key-nya ke siapa pun, termasuk ke saya.", file=sys.stderr)
        return 2
    log(f"wallet={wallet} (alamat saja yang dicatat, keypair tidak pernah dicatat)")
    if not acquire_lock(wallet):
        return 2
    # Login awal: kalau server Folester lagi down (HTTP 502/503 dsb.) atau
    # jaringan putus, JANGAN keluar — tunggu 60 dtk lalu coba login lagi,
    # tanpa batas, sampai server pulih. Bot baru berhenti kalau errornya
    # fatal (4xx: signature salah, wallet banned, tidak lolos syarat,
    # pesan login tidak dikenal) — itu dilempar sebagai RuntimeError biasa
    # dan tetap BERHENTI seperti dulu.
    # Alasan: 2026-11-23 ~19:02 WIB server Folester 502 di SEMUA endpoint
    # (home/nonce/frames, Cloudflare 502 Bad Gateway), bot sudah retry 5x
    # di http_json lalu BERHENTI, padahal yang mati servernya — bot harus
    # tetap hidup supaya langsung jalan lagi begitu server pulih, tanpa
    # Berly harus restart manual. Ctrl+C tetap mematikan bot.
    while True:
        try:
            sign_in(wallet, seed)
            player = ensure_joined(wallet)
            break
        except _RetryableError as e:
            log(f"Folester lagi down / jaringan gagal saat login ({e}), coba lagi 60 dtk lagi — bot tetap jalan")
            time.sleep(60)
    balance = float(player.get("balance") or 0)
    log(f"pengaturan: amount={a.amount:g} ANUL, beli {a.buy_delay:g} dtk setelah launch, "
        f"auto-sell {a.auto_sell_delay:g} dtk, interval {a.interval:g} dtk, max {a.max_buys}x, budget {a.budget:g}, reserve {a.reserve:g}")
    if balance < 0:
        log(f"PERINGATAN: saldo server NEGATIF ({balance:.2f} ANUL) — bot tidak "
            f"akan beli sampai saldo pulih di atas reserve. Cek dashboard "
            f"Folester / jual posisi manual, lalu bot lanjut sendiri.")
    elif balance - a.amount < a.reserve:
        log(f"PERINGATAN: saldo {balance:.2f} ANUL di bawah reserve+amount — "
            f"bot memantau dulu, beli jalan otomatis kalau saldo pulih.")
    # SPEED-2: ukur selisih jam HP vs server sekali saat start; semua umur
    # Frame di loop utama dikoreksi dengan angka ini (lihat `now = ...`).
    time_offset = _server_time_offset()
    log(f"jam HP vs server: selisih {time_offset:+.1f} dtk (umur Frame dikoreksi)")
    if a.check_only:
        log("check-only selesai, tidak ada pembelian")
        return 0

    seen = set()
    pending = {}  # frame_id -> {frame, created, next_try}: antre retry launch_wait
    latest_by_id = {}  # frame_id -> objek Frame TERBARU (WS/poll), untuk cek bukan-pertama
    pending_sells = {}  # frame_id -> {frame, amount, next_try, deadline}: antre auto-sell
    spent, buys = 0.0, 0
    state = {"reauth_done": False, "last_pause_log": 0.0,
             "paused_reason": "", "last_buy_error": "",
             "last_buy_error_at": 0.0}
    first = True
    polls = 0
    last_beat = time.monotonic()
    latest_ts, latest_name = "", "-"
    ws_queue = queue.Queue()
    ws_status = {"connected": False, "last_msg": 0.0, "reconnects": 0}
    ws_stop = threading.Event()
    ws_thread = None
    if not a.no_ws and not a.once and not a.check_only:
        ws_thread = threading.Thread(target=ws_listen,
                                     args=(ws_queue, ws_status, ws_stop),
                                     daemon=True)
        ws_thread.start()

    def _retry_delay(status):
        if status == "trade_cooldown":
            return TRADE_COOLDOWN_RETRY
        if status == "retryable":
            return 2.0
        return a.launch_wait_retry

    def schedule_sell(f, buy_result):
        """Antrekan auto-sell: jual semua token hasil beli ini sekian detik
        lagi. Tidak dipakai kalau --auto-sell-delay 0."""
        if a.auto_sell_delay <= 0:
            return
        base_amt = _num(buy_result.get("base"))
        if base_amt <= 0:
            log(f"auto-sell {f['name']} dilewati: jumlah token dari hasil beli tidak jelas ({buy_result.get('base')})")
            return
        at = time.monotonic() + a.auto_sell_delay
        pending_sells[f["id"]] = {"frame": f, "amount": base_amt,
                                  "next_try": at,
                                  "deadline": at + SELL_MAX_WAIT}
        log(f"auto-sell {f['name']} dijadwalkan {a.auto_sell_delay:g} dtk lagi ({base_amt:g} token)")

    def on_buy_success(f, r):
        nonlocal buys, spent, balance
        buys += 1
        spent += a.amount
        state["paused_reason"] = ""
        # SPEED-2: sesudah beli, JANGAN panggil get_me kalau ada retry beli
        # lain yang jatuh tempo <5 dtk lagi — get_me memegang _KA_LOCK dan
        # memblokir loop ~0,5-1 dtk, bisa menunda tembakan Frame berikutnya
        # (kasus 3 Frame launching berbarengan: CUTIE/NVIDIA/FLUFFY).
        # Saldo cukup dikurangi amount; refresh 60 dtk akan meluruskan.
        _retry_soon = any(p["next_try"] - time.monotonic() < 5.0 for p in pending.values())
        if _retry_soon:
            balance -= a.amount
        else:
            try:
                balance = _balance_from_me(get_me(wallet), balance - a.amount)
            except Exception as e:
                # Saldo gagal dibaca sesudah beli JANGAN mematikan bot: pakai
                # perkiraan (saldo lama - amount), refresh berikutnya (tiap
                # 60 dtk) akan meluruskan lagi dari server.
                log(f"saldo gagal diperbarui sesudah BUY {f['name']}: {e} "
                    f"(pakai perkiraan {balance - a.amount:.2f})")
                balance -= a.amount
        schedule_sell(f, r)

    def process_frame(f, now, is_live=False):
        """Satu Frame kandidat -> beli kalau lolos semua syarat.
        Dipakai jalur websocket (live) dan polling (cadangan) dengan aturan
        yang sama persis. TIDAK PERNAH mematikan bot: kalau belum boleh
        beli (saldo/reserve/budget/max_buys, terlalu dini, launch_wait),
        Frame dijadwalkan ulang ke antrean dan bot tetap memantau."""
        nonlocal buys, spent, balance, latest_ts, latest_name
        # SKIP-IF-NOT-FIRST PATCH: simpan SELALU data Frame terbaru, walau
        # id sudah seen — update WS/poll sesudah deteksi pertama (mis. trade
        # pembeli lain) harus tercatat, kalau tidak bot membeli buta dengan
        # data lama (harga 0,001 / trades=0) padahal harga sudah naik.
        latest_by_id[f["id"]] = f
        ts = f.get("created_at") or ""
        if ts > latest_ts:
            latest_ts = ts
            latest_name = f.get("name", "?")
        if f["id"] in seen:
            return False
        seen.add(f["id"])
        if first and not is_live:
            return False  # poll pertama cuma seeding, jangan beli riwayat lama
        try:
            created = datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
        except ValueError:
            return False
        age = (now - created).total_seconds()
        if age < -30 or age > a.max_age:
            return False
        if age < 0:
            age = 0  # jam HP sedikit tertinggal dari server, anggap baru lahir
        # Terlalu dini (umur < buy_delay): JADWALKAN, jangan tidur blokir
        # di loop utama — tidur di sini dulu menghentikan deteksi Frame
        # baru, retry, dan auto-sell selama buy_delay.
        if age < a.buy_delay:
            pending[f["id"]] = {"frame": f, "created": created,
                                "next_try": time.monotonic() + (a.buy_delay - age)}
            return False
        # Belum boleh beli (saldo/reserve/budget/max_buys): JEDA, bukan
        # STOP. Frame dijadwalkan ulang tiap 10 dtk sampai umurnya lewat
        # max_age — kalau saldo pulih (mis. Berly jual posisi manual),
        # beli jalan sendiri tanpa restart bot.
        reason = _limits_reason(buys, spent, balance, a)
        if reason:
            _log_pause(state, reason)
            pending[f["id"]] = {"frame": f, "created": created,
                                "next_try": time.monotonic() + 10}
            return False
        src = "WS" if is_live else "poll"
        log(f"FRAME BARU {f['name']} umur={age:.1f} dtk harga={f['price']:.6f} ANUL trades={f.get('trades', 0)} [{src}]")
        skip = _not_first_reason(latest_by_id, f["id"], f)
        if skip:
            log(f"SKIP {f['name']}: bukan pembeli pertama — {skip}, tidak beli")
            return False
        status, r = buy(f, a.amount, wallet, seed, state)
        if status == "ok":
            on_buy_success(f, r)
        elif status in ("launch_wait", "trade_cooldown", "retryable"):
            # Server belum membuka trading (launch_wait) / kena jeda antar
            # trade / gagal sesaat: antrekan ulang sampai umurnya melewati
            # max_age. launch_wait dijadwalkan ke umur 30,5 dtk (saat
            # trading dibuka), bukan tiap 0,5 dtk sejak umur 0,5 dtk.
            if status == "launch_wait":
                delay = _launch_wait_delay(created, now)
            else:
                delay = _retry_delay(status)
            pending[f["id"]] = {"frame": f, "created": created,
                                "next_try": time.monotonic() + delay}
            log(f"antre retry {f['name']} ({status}), coba lagi {delay:g} dtk lagi")
        else:
            # 'fail' = penolakan permanen server untuk Frame ini; sudah
            # dicatat lengkap di _do_trade, Frame tidak dicoba lagi.
            pass
        return False

    def retry_pending(now):
        """Coba lagi Frame yang antre (terlalu dini / launch_wait /
        cooldown / gagal sesaat / jeda saldo). TIDAK PERNAH mematikan bot:
        kalau batas belum pulih, antrean ditunda 10 dtk dan dicek lagi."""
        nonlocal buys, spent, balance
        for fid in list(pending.keys()):
            p = pending[fid]
            if time.monotonic() < p["next_try"]:
                continue
            age = (now - p["created"]).total_seconds()
            if age > a.max_age:
                log(f"STOP retry {p['frame']['name']}: umur {age:.0f} dtk > max_age {a.max_age}")
                del pending[fid]
                continue
            reason = _limits_reason(buys, spent, balance, a)
            if reason:
                _log_pause(state, reason)
                p["next_try"] = time.monotonic() + 10
                continue
            # SKIP-IF-NOT-FIRST PATCH: sebelum tembak di umur 30 dtk, cek
            # data terbaru — kalau ada yang sudah beli duluan (trades>0 /
            # harga naik >1,5x), jangan jadi exit liquidity mereka.
            skip = _not_first_reason(latest_by_id, fid, p["frame"])
            if skip:
                log(f"SKIP {p['frame']['name']}: bukan pembeli pertama — {skip}, tidak beli")
                del pending[fid]
                continue
            log(f"retry BUY {p['frame']['name']} (umur {age:.0f} dtk)")
            status, r = buy(p["frame"], a.amount, wallet, seed, state)
            if status == "ok":
                on_buy_success(p["frame"], r)
                del pending[fid]
            elif status in ("launch_wait", "trade_cooldown", "retryable"):
                if status == "launch_wait":
                    delay = _launch_wait_delay(p["created"], now)
                else:
                    delay = _retry_delay(status)
                p["next_try"] = time.monotonic() + delay
            else:
                del pending[fid]
        return False

    def process_sells():
        """Jual posisi yang sudah waktunya (auto-sell). Tidak menghentikan bot."""
        nonlocal spent, balance
        for fid in list(pending_sells.keys()):
            s = pending_sells[fid]
            if time.monotonic() < s["next_try"]:
                continue
            if time.monotonic() > s["deadline"]:
                log(f"auto-sell {s['frame']['name']} BERHENTI: tidak berhasil sampai batas waktu, posisi ditahan (jual manual)")
                del pending_sells[fid]
                continue
            status, r, lock = sell(s["frame"], s["amount"], wallet, seed, state)
            if status == "ok":
                spent = max(0.0, spent - (_num(r.get("quote")) - _num(r.get("fee"))))
                try:
                    balance = _balance_from_me(get_me(wallet), balance)
                except Exception as e:
                    log(f"saldo gagal diperbarui sesudah sell: {e}")
                del pending_sells[fid]
            elif status in ("launch_wait", "trade_cooldown", "retryable"):
                s["next_try"] = time.monotonic() + _retry_delay(status)
            elif status == "position_locked":
                avail = _num((lock or {}).get("available_qty"))
                if 0 < avail < s["amount"]:
                    log(f"auto-sell {s['frame']['name']}: posisi terkunci sebagian, jual {avail:g} token saja")
                    s["amount"] = avail
                    s["next_try"] = time.monotonic() + 1.0
                elif avail <= 0:
                    log(f"auto-sell {s['frame']['name']}: posisi terkunci semua, coba lagi {SELL_LOCK_RETRY:g} dtk lagi")
                    s["next_try"] = time.monotonic() + SELL_LOCK_RETRY
                else:
                    s["next_try"] = time.monotonic() + 1.0
            else:
                log(f"auto-sell {s['frame']['name']} GAGAL, posisi ditahan (jual manual)")
                del pending_sells[fid]

    last_poll = 0.0
    last_balance_refresh = time.monotonic()
    while True:
        # Refresh saldo tiap 60 dtk dari server (request kecil, bukan daftar
        # Frame 1 MB): saldo di heartbeat tidak lagi basi berjam-jam, dan
        # jeda karena saldo habis bisa pulih sendiri tanpa restart.
        # WARM-UP PATCH: refresh DITUNDA kalau ada retry beli yang jatuh
        # tempo <5 dtk lagi — get_me di sini bisa memblokir loop utama
        # ~1 dtk dan bikin retry umur 30 dtk telat.
        _refresh_soon = any(
            p["next_try"] - time.monotonic() < 5.0 for p in pending.values())
        if time.monotonic() - last_balance_refresh >= 60 and not _refresh_soon:
            last_balance_refresh = time.monotonic()
            try:
                balance = _balance_from_me(get_me(wallet), balance)
            except Exception as e:
                log(f"refresh saldo gagal: {e} (pakai saldo terakhir {balance:.2f})")
        if a.heartbeat > 0 and time.monotonic() - last_beat >= a.heartbeat:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))).total_seconds()
                age_s = f"{age:.0f} dtk lalu"
            except (ValueError, TypeError):
                age_s = "?"
            ws_bit = ""
            if ws_thread is not None:
                ws_bit = " | ws: OK" if ws_status["connected"] else " | ws: PUTUS"
            extra = ""
            if state.get("paused_reason"):
                extra += f" | JEDA: {state['paused_reason']}"
            if state.get("last_buy_error") and time.monotonic() - state.get("last_buy_error_at", 0) < 300:
                extra += f" | gagal terakhir: {state['last_buy_error'][:60]}"
            ka_bit = ""
            if _KA_STATS["fresh"] or _KA_STATS["reused"]:
                ka_bit = (f" | ka: {_KA_STATS['fresh']} baru/"
                          f"{_KA_STATS['reused']} pakai-ulang/"
                          f"{_KA_STATS['reconnect']} sambung-ulang")
            log(f"memantau... cek ke-{polls} | Frame terbaru: {latest_name} ({age_s}) | beli: {buys} | saldo: {balance:.2f} ANUL (perkiraan){ws_bit}{extra}{ka_bit}")
            last_beat = time.monotonic()
        # 1. Jalur websocket: Frame yang masuk live diproses dulu (paling cepat).
        # Loop ini bangun tiap 0.01 dtk supaya antrean WS langsung diproses,
        # tidak menunggu polling 30 detik. (SPEED PATCH: 0.2 -> 0.05 dtk,
        # MAX PATCH: 0.05 -> 0.01 dtk — deteksi WS sampai 40 ms lebih cepat;
        # biaya baterai kecil, loop tiap putaran cuma cek antrean kosong.)
        now = datetime.now(timezone.utc) + timedelta(seconds=time_offset)
        while True:
            try:
                f = ws_queue.get_nowait()
            except queue.Empty:
                break
            if process_frame(f, now, is_live=True):
                ws_stop.set()
                return 0
        # 2a. PEMANASAN (WARM-UP PATCH): kalau ada retry beli yang jatuh
        # tempo <=1,5 dtk lagi dan koneksinya belum dipanaskan untuk Frame
        # ini, kirim satu request kecil (get_me) SEKARANG. Tujuannya
        # supaya koneksi keep-alive hangat / tersambung ulang SEBELUM
        # detik 30 — bukan pas detik 30, saat sambung-ulang + TLS bisa
        # makan ~1 dtk dan harga sudah naik 3x. Sekali per Frame saja;
        # gagal pemanasan tidak menghentikan apa pun (retry tetap jalan).
        for _p in list(pending.values()):
            _dt = _p["next_try"] - time.monotonic()
            if 0 < _dt <= 1.5 and not _p.get("warmed"):
                _p["warmed"] = True
                try:
                    get_me(wallet)
                    log(f"pemanasan koneksi {_p['frame']['name']} OK")
                except Exception as e:
                    log(f"pemanasan koneksi {_p['frame']['name']} gagal "
                        f"({e}), retry tetap jalan")
        # 2. Retry Frame yang masih launch_wait (tanpa blokir deteksi baru).
        if retry_pending(now):
            ws_stop.set()
            return 0
        # 3. Auto-sell posisi yang sudah waktunya.
        process_sells()
        # 4. Jalur polling cadangan tiap a.interval detik: daftar lengkap,
        # kalau WS ketinggalan. DITUNDA kalau ada retry yang jatuh tempo
        # <10 dtk lagi — fetch polling 1 MB / 2-3 dtk akan memblokir retry
        # di jendela buka 30 dtk dan bikin bot kalah balapan. (WARM-UP
        # PATCH: 3 -> 10 dtk, karena fetch yang mulai di umur 27 dtk
        # pun masih bisa menunda retry umur 30 dtk.)
        _retry_soon = any(
            p["next_try"] - time.monotonic() < 10.0 for p in pending.values())
        if time.monotonic() - last_poll >= a.interval and not _retry_soon:
            last_poll = time.monotonic()
            try:
                frames = fetch_frames()
            except Exception as e:
                log(f"poll gagal: {e}")
                if a.once:
                    ws_stop.set()
                    return 1
            else:
                polls += 1
                now = datetime.now(timezone.utc) + timedelta(seconds=time_offset)
                # Frame WS yang masuk selama fetch polling (1 MB, 2-3 dtk)
                # diproses dulu — jangan tunggu putaran loop berikut.
                while True:
                    try:
                        f = ws_queue.get_nowait()
                    except queue.Empty:
                        break
                    if process_frame(f, now, is_live=True):
                        ws_stop.set()
                        return 0
                for f in frames:
                    if process_frame(f, now):
                        ws_stop.set()
                        return 0
            first = False
            if a.once:
                log(f"once selesai: buys={buys} spent={spent:.2f}")
                ws_stop.set()
                return 0
        # SPEED-3: spin-wait 0,1 dtk terakhir sebelum retry beli — jangan
        # tidur 0,05 dtk dan kelewatan target sampai 50 ms. Loop ini muter
        # kosong (tanpa tidur) sampai waktunya tiba, lalu langsung balik ke
        # atas loop (retry_pending) tanpa tidur. CPU yang dipakai cuma
        # ~0,1 dtk per Frame, jadi tidak boros baterai.
        _spin_until = min((p["next_try"] for p in pending.values()), default=None)
        if _spin_until is not None and 0 < _spin_until - time.monotonic() <= 0.1:
            while time.monotonic() < _spin_until:
                pass
            continue
        time.sleep(0.01)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"BERHENTI: {e}", file=sys.stderr)
        raise SystemExit(1)

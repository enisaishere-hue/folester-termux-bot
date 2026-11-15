#!/usr/bin/env python3
# ============================================================================
# Folester Frames TESTNET auto-buy — Termux (jalan di HP Berly, BUKAN di server)
# ============================================================================
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
#        1,1 detik setelah launching). Bot langsung beli.
#     2. Polling daftar Frame tiap 30 detik — jalur CADANGAN. Kalau websocket
#        putus, polling tetap jalan, jadi bot tidak pernah buta. Websocket
#        yang putus disambung lagi otomatis (backoff 1-30 dtk).
#   Bot jalan TERUS (nonstop) sampai batas aman tercapai:
#   50 kali beli / total 5.000 ANUL / saldo di bawah 100 ANUL.
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
#   - "Pembeli pertama" tidak bisa dijamin: trade pertama sebuah Frame
#     mendarat ~1 detik setelah dibuat (biasanya AI trader situs / kreator),
#     dan bot websocket membeli sesaat setelah trade pertama itu terlihat —
#     jadi bot biasanya pembeli ke-2/ke-3, bukan ke-1. Polling saja lebih
#     lambat (~2-4 detik).
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
# OPSI (boleh diubah):
#   --amount 100     = beli 100 ANUL tiap Frame baru (minimal 1)
#   --interval 30    = cek daftar Frame tiap 30 detik (jalur polling cadangan)
#   --no-ws          = matikan websocket, cuma pakai polling (kalau WS bermasalah)
#   --max-buys 50    = berhenti setelah 50 kali beli
#   --budget 5000    = berhenti setelah total belanja 5.000 ANUL
#   --reserve 100    = berhenti kalau saldo ANUL di bawah 100
#   --max-age 120    = cuma beli Frame yang umurnya <=120 detik saat ketemu
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
from datetime import datetime, timezone
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


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
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


def _py_json(url, method="GET", data=None, use_cookies=False):
    """Satu request JSON lewat http.client (Python murni)."""
    u = urlparse(url)
    host, port = u.hostname, u.port or 443
    path = u.path or "/"
    if u.query:
        path += "?" + u.query
    headers = {"User-Agent": UA, "Accept": "application/json",
               "Accept-Encoding": "gzip"}
    body = None
    if method == "POST":
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode() if data is not None else b"{}"
    cookies = _read_cookies() if use_cookies else {}
    if cookies:
        headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    conn = None
    try:
        raw = _raw_connect(host, port)
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(raw, server_hostname=host)
        ss.settimeout(20)
        conn = http.client.HTTPSConnection(host, port, timeout=20)
        conn.sock = ss
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw_body = resp.read()
        if resp.getheader("Content-Encoding") == "gzip":
            try:
                raw_body = gzip.decompress(raw_body)
            except (OSError, EOFError) as e:
                raise _RetryableError(f"http {method} {url} gagal dekompresi gzip: {e}")
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
    except (OSError, socket.timeout, ssl.SSLError,
            http.client.HTTPException) as e:
        raise _RetryableError(f"http {method} {url} gagal: {e}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
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


def http_json(url, method="GET", data=None, use_cookies=False):
    """Request JSON: coba Python murni dulu, kalau gagal coba curl.
    Gagal sesaat dicoba ulang (5x, jeda 1/2/4/8 dtk); error 4xx (login salah,
    tidak lolos syarat, dsb.) langsung gagal supaya tidak buang waktu."""
    last_err = RuntimeError(f"http {method} {url} gagal tanpa balasan")
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        for backend in (_py_json, _curl_json):
            try:
                return backend(url, method, data, use_cookies)
            except _RetryableError as e:
                last_err = e
                continue
        if attempt < RETRY_ATTEMPTS:
            wait = 2 ** (attempt - 1)
            log(f"jaringan gagal ({last_err}), coba lagi {attempt + 1}/{RETRY_ATTEMPTS} setelah {wait} dtk")
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


def _raw_connect(host, port):
    """Koneksi TCP. Coba langsung dulu; kalau gagal dan ada proxy di env
    (VM Muse), lewat CONNECT proxy itu. Di Termux tidak ada proxy env,
    jadi selalu langsung. Kredensial proxy dibaca dari env saat jalan,
    tidak pernah dicetak atau disimpan."""
    try:
        return socket.create_connection((host, port), timeout=15)
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
            ss.settimeout(5)
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
    d = http_json(f"{BASE}/api/play/frames?sort=created_at&q=")
    frames = sorted(d.get("frames", []), key=lambda f: f["created_at"])
    return frames


def buy(frame, amount, wallet, seed, state):
    body = {"frameId": frame["id"], "side": "buy", "amount": amount}
    try:
        r = http_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True)
    except RuntimeError as e:
        if "sign_in_required" in str(e) and not state.get("reauth_done"):
            log("sesi habis, login ulang...")
            sign_in(wallet, seed)
            state["reauth_done"] = True
            try:
                r = http_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True)
            except RuntimeError as e2:
                log(f"BUY {frame['name']} gagal HTTP: {e2}")
                return None
        else:
            log(f"BUY {frame['name']} gagal HTTP: {e}")
            return None
    if isinstance(r, dict) and r.get("error") == "sign_in_required" and not state.get("reauth_done"):
        log("sesi habis, login ulang...")
        sign_in(wallet, seed)
        state["reauth_done"] = True
        try:
            r = http_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True)
        except RuntimeError as e:
            log(f"BUY {frame['name']} gagal HTTP: {e}")
            return None
    if isinstance(r, dict) and r.get("error"):
        log(f"BUY {frame['name']} ditolak: {r}")
        return None
    log(f"BUY {frame['name']} amount={amount} ANUL -> dapat {r.get('base')} token, "
        f"harga {r.get('quote')} ANUL, fee {r.get('fee')}")
    return r


def main():
    ap = argparse.ArgumentParser(description="Folester testnet auto-buy (Termux)")
    ap.add_argument("--keypair", required=True, help="path file keypair Solana, mis. ~/.config/solana/id.json")
    ap.add_argument("--amount", type=float, default=100, help="ANUL per Frame baru (min 1)")
    ap.add_argument("--interval", type=float, default=30, help="detik antar cek polling cadangan (deteksi cepat lewat websocket; polling cuma cadangan kalau WS putus)")
    ap.add_argument("--heartbeat", type=float, default=3, help="detik antar kabar berkala di log (0 = mati)")
    ap.add_argument("--no-ws", action="store_true", help="matikan websocket, cuma pakai polling")
    ap.add_argument("--max-buys", type=int, default=50, help="berhenti setelah sekian beli")
    ap.add_argument("--budget", type=float, default=5000, help="total ANUL maksimal yang dibelanjakan")
    ap.add_argument("--reserve", type=float, default=100, help="berhenti kalau saldo < ini")
    ap.add_argument("--max-age", type=int, default=120, help="cuma beli Frame umur <= sekian detik")
    ap.add_argument("--once", action="store_true", help="cek sekali lalu keluar")
    ap.add_argument("--check-only", action="store_true", help="cuma login + cek saldo, tanpa beli")
    a = ap.parse_args()
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
    sign_in(wallet, seed)
    player = ensure_joined(wallet)
    balance = float(player.get("balance") or 0)
    if a.check_only:
        log("check-only selesai, tidak ada pembelian")
        return 0

    seen = set()
    spent, buys = 0.0, 0
    state = {"reauth_done": False}
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

    def process_frame(f, now, is_live=False):
        """Satu Frame kandidat -> beli kalau lolos semua syarat.
        Dipakai jalur websocket (live) dan polling (cadangan) dengan aturan
        yang sama persis. Kembalikan True kalau bot harus STOP."""
        nonlocal buys, spent, balance, latest_ts, latest_name
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
        if age < 0 or age > a.max_age:
            return False
        # balance adalah saldo LIVE (diperbarui dari server tiap selesai beli),
        # jadi cadangan dicek dari saldo setelah beli ini, bukan saldo dikurangi
        # spent (itu menghitung dobel dan membuat bot berhenti terlalu cepat).
        if buys >= a.max_buys or spent + a.amount > a.budget or balance - a.amount < a.reserve:
            log(f"STOP: buys={buys} spent={spent:.2f} saldo~{balance:.2f}")
            return True
        src = "WS" if is_live else "poll"
        log(f"FRAME BARU {f['name']} umur={age:.0f} dtk harga={f['price']:.6f} ANUL trades={f.get('trades', 0)} [{src}]")
        r = buy(f, a.amount, wallet, seed, state)
        if r:
            buys += 1
            spent += a.amount
            balance = float(get_me(wallet).get("player", {}).get("balance") or balance - a.amount)
        return False

    while True:
        if a.heartbeat > 0 and time.monotonic() - last_beat >= a.heartbeat:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(latest_ts.replace("Z", "+00:00"))).total_seconds()
                age_s = f"{age:.0f} dtk lalu"
            except (ValueError, TypeError):
                age_s = "?"
            ws_bit = ""
            if ws_thread is not None:
                ws_bit = " | ws: OK" if ws_status["connected"] else " | ws: PUTUS"
            log(f"memantau... cek ke-{polls} | Frame terbaru: {latest_name} ({age_s}) | beli: {buys} | saldo: ~{balance:.2f} ANUL{ws_bit}")
            last_beat = time.monotonic()
        # 1. Jalur websocket: Frame yang masuk live diproses dulu (paling cepat).
        now = datetime.now(timezone.utc)
        while True:
            try:
                f = ws_queue.get_nowait()
            except queue.Empty:
                break
            if process_frame(f, now, is_live=True):
                ws_stop.set()
                return 0
        # 2. Jalur polling cadangan: daftar lengkap, kalau WS ketinggalan.
        try:
            frames = fetch_frames()
        except Exception as e:
            log(f"poll gagal: {e}")
            if a.once:
                ws_stop.set()
                return 1
            time.sleep(a.interval)
            continue
        polls += 1
        now = datetime.now(timezone.utc)
        for f in frames:
            if process_frame(f, now):
                ws_stop.set()
                return 0
        first = False
        if a.once:
            log(f"once selesai: buys={buys} spent={spent:.2f}")
            ws_stop.set()
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"BERHENTI: {e}", file=sys.stderr)
        raise SystemExit(1)

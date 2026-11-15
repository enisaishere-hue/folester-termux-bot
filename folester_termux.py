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
#   Bot jalan TERUS (poll tiap 5 detik, nonstop) sampai batas aman tercapai:
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
#   - "Pembeli pertama" tidak bisa dijamin: situsnya sendiri punya AI trader
#     dan buy pertama sering mendarat ~2 detik setelah Frame dibuat.
#   - Script ini cuma BELI. Jual tetap manual dari HP kamu.
#   - Wallet yang dipakai HARUS lolos 3 dari 4 syarat Folester: umur >=90 hari,
#     >=20 hari aktif, >=50 transaksi, saldo >=0,01 SOL. Wallet baru TIDAK
#     lolos — pakai wallet Solana lamamu.
#
# KEBUTUHAN DI TERMUX (sekali saja):
#   pkg install python curl
#
# CARA JALANIN (ketik di Termux, satu baris tiap perintah):
#   1. Cek dulu (tanpa beli):  python3 folester_termux.py --keypair ~/.config/solana/id.json --check-only
#   2. Jalanin beneran:       python3 folester_termux.py --keypair ~/.config/solana/id.json --amount 100
#   3. Biar tetap jalan saat layar mati:  termux-wake-lock
#      lalu jalankan dengan:  nohup python3 folester_termux.py --keypair ~/.config/solana/id.json --amount 100 > folester.log 2>&1 &
#   4. Berhenti:  pkill -f folester_termux.py
#
# OPSI (boleh diubah):
#   --amount 100     = beli 100 ANUL tiap Frame baru (minimal 1)
#   --interval 5     = cek daftar Frame tiap 5 detik
#   --max-buys 50    = berhenti setelah 50 kali beli
#   --budget 5000    = berhenti setelah total belanja 5.000 ANUL
#   --reserve 100    = berhenti kalau saldo ANUL di bawah 100
#   --max-age 120    = cuma beli Frame yang umurnya <=120 detik saat ketemu
#   --once           = cek sekali lalu keluar (buat ngetes)
# ============================================================================
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

BASE = "https://www.folester.xyz"
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36"
COOKIE_FILE = os.path.expanduser("~/.folester_session_cookies.txt")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "folester_termux.log")

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
# HTTP via curl (urllib kena HTTP 403 dari Folester; curl + UA browser lolos)
# ---------------------------------------------------------------------------
def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def curl_json(url, method="GET", data=None, use_cookies=False):
    cmd = ["curl", "-s", "--max-time", "20", "-A", UA, "-w", "\n%{http_code}"]
    if use_cookies:
        cmd += ["-b", COOKIE_FILE, "-c", COOKIE_FILE]
    if method == "POST":
        cmd += ["-X", "POST", "-H", "content-type: application/json"]
        if data is not None:
            cmd += ["-d", json.dumps(data)]
    cmd.append(url)
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise RuntimeError(f"curl {method} {url} gagal rc={out.returncode}: {out.stderr.strip()[:200]}")
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
        raise RuntimeError(f"HTTP {code} dari {url}: {detail}")
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"balasan bukan JSON dari {url}: {body[:200]}")


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
    d = curl_json(f"{BASE}/api/auth/nonce", method="POST", data={"wallet": wallet})
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
    r = curl_json(f"{BASE}/api/auth/verify", method="POST",
                  data={"wallet": wallet, "nonce": nonce, "message": message,
                        "signature": sig_b64}, use_cookies=True)
    if isinstance(r, dict) and r.get("error"):
        raise RuntimeError(f"verify gagal: {r}")
    log(f"login OK wallet={wallet[:4]}...{wallet[-4:]}")
    return True


def get_me(wallet):
    return curl_json(f"{BASE}/api/play/me?wallet={wallet}", use_cookies=True)


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
        s = curl_json(f"{BASE}/api/scan", method="POST", data={}, use_cookies=True)
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
    r = curl_json(f"{BASE}/api/play/join", method="POST", data={}, use_cookies=True)
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
    d = curl_json(f"{BASE}/api/play/frames?sort=created_at&q=")
    frames = sorted(d.get("frames", []), key=lambda f: f["created_at"])
    return frames


def buy(frame, amount, wallet, seed, state):
    body = {"frameId": frame["id"], "side": "buy", "amount": amount}
    try:
        r = curl_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True)
    except RuntimeError as e:
        if "sign_in_required" in str(e) and not state.get("reauth_done"):
            log("sesi habis, login ulang...")
            sign_in(wallet, seed)
            state["reauth_done"] = True
            try:
                r = curl_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True)
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
            r = curl_json(f"{BASE}/api/play/trade", method="POST", data=body, use_cookies=True)
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
    ap.add_argument("--interval", type=int, default=5, help="detik antar cek")
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
    while True:
        try:
            frames = fetch_frames()
        except Exception as e:
            log(f"poll gagal: {e}")
            if a.once:
                return 1
            time.sleep(a.interval)
            continue
        now = datetime.now(timezone.utc)
        for f in frames:
            if f["id"] in seen:
                continue
            seen.add(f["id"])
            if first:
                continue  # poll pertama cuma seeding, jangan beli riwayat lama
            try:
                created = datetime.fromisoformat(f["created_at"].replace("Z", "+00:00"))
            except ValueError:
                continue
            age = (now - created).total_seconds()
            if age < 0 or age > a.max_age:
                continue
            if buys >= a.max_buys or spent + a.amount > a.budget or balance - spent < a.reserve:
                log(f"STOP: buys={buys} spent={spent:.2f} saldo~{balance - spent:.2f}")
                return 0
            log(f"FRAME BARU {f['name']} umur={age:.0f} dtk harga={f['price']:.6f} ANUL trades={f['trades']}")
            r = buy(f, a.amount, wallet, seed, state)
            if r:
                buys += 1
                spent += a.amount
                balance = float(get_me(wallet).get("player", {}).get("balance") or balance - a.amount)
        first = False
        if a.once:
            log(f"once selesai: buys={buys} spent={spent:.2f}")
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as e:
        print(f"BERHENTI: {e}", file=sys.stderr)
        raise SystemExit(1)

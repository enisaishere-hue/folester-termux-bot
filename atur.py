#!/usr/bin/env python3
"""Atur bot Folester secara interaktif (Bahasa Indonesia).
Jalankan: python3 atur.py — jawab pertanyaan, Enter = pakai nilai lama.
Menyimpan ke config.json di folder yang sama. Setelah itu jalankan bot
dengan: ./mulai  (atau: python3 bot.py)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(HERE, "config.json")

DEFAULTS = {
    "keypair": "~/bacj-key.txt",
    "amount": 100,
    "buy_delay": 0.5,
    "auto_sell_delay": 0,
    "interval": 30,
    "max_buys": 50,
    "reserve": 100,
}


def _load():
    try:
        with open(CFG_PATH) as f:
            cfg = json.load(f)
            return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}


def _cek_keypair(path):
    """Cek file keypair bisa dibaca bot (JSON 64 angka atau 1 baris base58).
    Kembalikan None kalau valid, atau pesan error kalau tidak."""
    try:
        sys.path.insert(0, HERE)
        import bot as _bot
        _bot.load_keypair(os.path.expanduser(path))
        return None
    except Exception as e:
        return str(e)


def _tanya_keypair(cfg):
    """Tanya path file keypair. Tolak private key langsung, path yang
    tidak ada, dan file yang isinya bukan keypair — bot hanya mau baca
    file keypair yang valid, bukan key yang ditempel."""
    lama = cfg.get("keypair", DEFAULTS["keypair"])
    while True:
        raw = input(f"File keypair (path file key di HP kamu) [{lama}]: ").strip()
        p = raw or lama
        # Private key langsung (base58 panjang tanpa /) — bukan path file.
        if "/" not in p and len(p) > 40:
            print("  Itu kelihatannya private key langsung, bukan path file.")
            print("  Bot tidak mau key yang ditempel. Simpan dulu ke file:")
            print("    cat > ~/wallet-key.txt   (lalu tempel key-nya, Enter, Ctrl+D)")
            print("  Lalu isi path filenya di sini, mis. ~/wallet-key.txt")
            continue
        if not os.path.isfile(os.path.expanduser(p)):
            print(f"  File tidak ditemukan: {p}")
            print("  Cek lagi path-nya, atau simpan dulu key-nya ke file.")
            continue
        err = _cek_keypair(p)
        if err:
            print(f"  File itu bukan keypair yang valid: {err}")
            print("  Isi file harus keypair Solana (JSON 64 angka) atau 1 baris private key base58.")
            continue
        return p


def _tanya(label, kunci, cfg, tipe=float):
    lama = cfg.get(kunci, DEFAULTS[kunci])
    while True:
        raw = input(f"{label} [{lama}]: ").strip()
        if raw == "":
            return lama
        try:
            # Terima koma desimal Indonesia (0,5) maupun titik (0.5).
            return tipe(raw.replace(",", "."))
        except ValueError:
            print("  Bukan angka yang benar, coba lagi.")


def main():
    cfg = _load()
    print("== Atur bot Folester ==")
    print("Tekan Enter untuk pakai nilai yang tertulis di [tanda kurung].")
    print()
    cfg["keypair"] = _tanya_keypair(cfg)
    cfg["amount"] = _tanya("Berapa ANUL tiap beli", "amount", cfg)
    cfg["buy_delay"] = _tanya("Beli berapa detik setelah launch", "buy_delay", cfg)
    cfg["auto_sell_delay"] = _tanya("Jual otomatis berapa detik setelah beli (0 = mati)", "auto_sell_delay", cfg)
    cfg["interval"] = _tanya("Cek Frame baru tiap berapa detik (polling cadangan)", "interval", cfg)
    cfg["max_buys"] = _tanya("Maksimal berapa kali beli", "max_buys", cfg, tipe=int)
    cfg["reserve"] = _tanya("Sisa saldo minimum (ANUL) — berhenti kalau saldo di bawah ini", "reserve", cfg)
    with open(CFG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
    os.chmod(CFG_PATH, 0o600)
    print()
    print("Tersimpan di config.json:")
    for k, v in cfg.items():
        print(f"  {k}: {v}")
    print()
    print("Jalankan bot dengan: ./mulai")
    print("Lihat log dengan: log")


if __name__ == "__main__":
    main()

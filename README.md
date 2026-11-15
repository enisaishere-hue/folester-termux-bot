# Folester Termux Auto-Buy

Bot auto-buy untuk **Folester Frames testnet** (https://www.folester.xyz/play),
jalan di **Termux di HP Android**. Begitu ada Frame (token) baru, bot langsung
beli pakai saldo `$ANUL` simulasi — bukan SOL asli, bukan transaksi blockchain.

## Cara kerja

1. Baca keypair Solana dari HP kamu sendiri (mis. `~/.config/solana/id.json`).
2. Minta nonce ke Folester, tanda tangani **pesan login gratis**
   (`folester.xyz wants you to sign in...`), verifikasi, dapat cookie sesi.
3. Cek syarat kelayakan wallet (umur, hari aktif, transaksi, saldo SOL),
   lalu join kalau belum terdaftar.
4. Poll daftar Frame tiap 0,5 detik. Kalau ada Frame baru (umur ≤ 120 detik),
   langsung beli **100 ANUL**. Berhenti setelah 50 kali beli, total 5.000 ANUL,
   atau saldo di bawah 100 ANUL. Kalau jaringan gagal sesaat (DNS, timeout,
   server sibuk), tiap request dicoba ulang 5x sebelum bot menyerah. Bot juga
   menulis kabar berkala tiap 3 detik di log (cek ke-berapa, Frame terbaru,
   jumlah beli, saldo) supaya kelihatan masih jalan; intervalnya bisa diubah
   dengan `--heartbeat` (0 = mati).

## Instal di Termux

```sh
pkg install python curl
curl -sL https://raw.githubusercontent.com/enisaishere-hue/folester-termux-bot/main/bot.py -o bot.py
```

Atau pakai git:

```sh
pkg install python curl git
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

Opsi lain: `--amount 100` (ANUL per Frame), `--interval 0.5` (detik antar cek),
`--max-buys 50`, `--budget 5000`, `--reserve 100`, `--max-age 120`,
`--once` (cek sekali), `--check-only` (cuma login + cek saldo).

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
- "Pembeli pertama" tidak bisa dijamin: situsnya sendiri punya AI trader dan
  buy pertama sering mendarat ~2 detik setelah Frame dibuat.
- Script ini cuma BELI. Jual tetap manual dari HP.

## Lisensi

MIT. Pakai dengan risiko sendiri.

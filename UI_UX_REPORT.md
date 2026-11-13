# Evy Kost — Laporan Audit & Perbaikan UI/UX (Branch `audit/product-ui-ux`)

**Untuk:** Product Manager
**Dari:** Raihan (dengan bantuan Command Code)
**Tanggal:** 5 Oktober 2026
**Status:** Selesai — **belum di-commit, belum di-push, belum deploy** (menunggu keputusan pemilik produk)

---

## 1. Ringkasan Eksekutif

Tim melakukan audit visual penuh aplikasi (Owner, Staff, Portal Tenant) langsung pada aplikasi yang **dirender**, bukan hanya membaca kode. Dari audit itu dijalankan serangkaian perbaikan terarah: komposisi mobile, keseragaman warna, aksesibilitas, keadaan kosong, dan satu **perbaikan bug alur pembayaran tenant**.

Hasil terukur:

- **Skor checkup: 25/60 → 40/60** (verdict awal *Block* → turun ke *Needs changes* setelah koreksi fakta; sisa temuan bersifat peningkatan, bukan penghalang).
- **1 bug perilaku bisnis ditemukan & diperbaiki**: portal tenant menampilkan **"LUNAS"** padahal invoice masih berstatus **menunggu verifikasi** (berpotensi membuat tenant mengira sudah selesai). Kini menampilkan "MENUNGGU VERIFIKASI" dengan penjelasan.
- **15 file berubah (+246/−87)** — semuanya template/CSS, plus **1 perubahan kecil Python** (`finance/views.py`, +5 baris) untuk bug di atas.
- **Full test suite hijau (exit code 0)** setelah semua perubahan; `manage.py check` bersih.
- **Tidak ada data produksi/dev yang disentuh.** Semua uji visual memakai **copy disposable** dari database development (skema dimigrasikan di copy, bukan di DB utama).

---

## 2. Konteks & Batasan

- Branch `audit/product-ui-ux` dibuat dari `68b05e3` (rangkaian sebelumnya: `9912bb5` baseline → `12b9b01` stabilisasi → `68b05e3` hardening konkurensi finansial). Branch ini **di atas** pekerjaan tersebut; 3 commit itu sudah ada, belum di-push.
- **Aturan yang dijaga ketat selama seluruh fase:** tidak deploy, tidak push, tidak merge, tidak mengubah data/kredensial production, tidak menyentuh DB development utama, tidak commit tanpa izin.
- Kredensial audit hanya ada di DB copy (dipegang Raihan); **tidak ditulis di laporan ini**.

## 3. Metode (ringkas)

1. **Environment visual disposable**: copy DB dev → migrasi di copy → akun audit (owner & staff) + state contoh (invoice MENUNGGU/TELAT/LUNAS, tiket, biaya operasional, PIN tenant). Server lokal `127.0.0.1:8765`.
2. **Walkthrough visual** dengan browser otomatis (Chrome via agent-browser): **37 screenshot** pada 3 ukuran (**1440px desktop, 768px tablet, 375px mobile**) untuk 3 peran; 15 di antaranya dianalisis visual mendalam; ditambah snapshot pohon aksesibilitas dan probe DOM.
   - Catatan: fitur "Design mode" Command Code Desktop tidak dapat dikendalikan dari sesi CLI ini → dicatat sebagai keterbatasan; bukti visual diambil lewat screenshot nyata (bukan tiruan).
3. **Tiga laporan diagnostik resmi** (report-only, ada di `.commandcode/design/`): `checkup` (kesehatan menyeluruh), `smell` (pola desain generik/AI), `review` (kritik pengalaman pengguna).
4. **Perbaikan bertahap** dengan verifikasi render ulang setelah setiap tahap (relayout → refine → finish), lalu **regresi penuh**.

## 4. Yang Terjadi (kronologi singkat)

| Tahap | Aktivitas | Hasil |
|---|---|---|
| A | Audit visual penuh + 3 laporan diagnostik | Checkup v1 25/60; smell 6/10; review 31/50 |
| B | **Koreksi integritas laporan** | Klaim awal "tabel tanpa wrapper responsive" ternyata salah (kesalahan pola pencarian saya). Setelah diverifikasi ulang: wrapper ada; masalah sebenarnya = aksi tabel tidak terlihat tanpa pan. Severity & verdict dikoreksi (Block → Needs changes) di ketiga laporan |
| C | **Relayout** | Tabel di <768px berubah jadi kartu berlabel — aksi (Setujui/Edit/Hapus/Respon) **selalu terlihat tanpa pan**; KPI diseragamkan (rail warna dihapus); sidebar hanya satu item aktif (bug "Kelola Staff selalu menyala" diperbaiki) |
| D | Insiden teknis | Server lama sempat menyajikan render basi → didiagnosis (probe DOM) & diperbaiki (restart); semua bukti verifikasi diambil ulang dengan cache-bust |
| E | **Refine (Settle)** | Bootstrap biru dihapus dari tombol/fokus/pagination/portal → **satu warna brand (indigo)**; warna semantik (hijau/merah/amber status) dipertahankan |
| F | **Finish** | Lihat §5 — termasuk **penemuan bug "LUNAS" palsu** saat verifikasi portal (dicek ke DB: invoice MENUNGGU tapi portal bilang LUNAS) |
| G | Regresi | `manage.py check` bersih; **full suite exit code 0**; semua server/browser dimatikan |

## 5. Temuan → Status

### Diperbaiki & terverifikasi (render nyata)

| # | Temuan | Dampak pengguna | Bukti perbaikan |
|---|---|---|---|
| 1 | **Portal menampilkan "LUNAS" saat invoice masih MENUNGGU** | Tenant bisa mengira pembayaran selesai → tidak menagih/konfirmasi | Kini "MENUNGGU VERIFIKASI — Bukti pembayaran Anda sedang diperiksa admin. Tidak perlu upload lagi." (screenshot + cek DB) |
| 2 | **Aksi tabel tidak terlihat di mobile** | Staff tidak bisa setujui/respon dari HP tanpa pan tersembunyi | Kartu berlabel + aksi terlihat; probe DOM 150/165/125/20/15 label ter-render |
| 3 | **Sidebar dua item aktif** ("Kelola Staff" di semua halaman `/staff/*`) | Orientasi navigasi kacau | Perbaikan kondisi rute; diverifikasi visual |
| 4 | **Label form tidak terhubung ke input** (portal & lapor) | Pembaca layar menyebut field dengan contoh ("Contoh: A-101") | Label `for/id`; nama aksesibilitas kini "LOKASI KOST/NOMOR KAMAR/PIN PEMBAYARAN" |
| 5 | **Dua warna primer bersaing** (biru Bootstrap vs indigo brand) | Terlihat "setengah jadi", kurang tepercaya | Satu indigo di CTA/fokus/pagination/portal (render report/tenant/invoice/portal) |
| 6 | **Hover lift pada kartu statis** (terlihat bisa diklik, padahal tidak) | Affordansi palsu | Efek dihapus |
| 7 | **Animasi tanpa `prefers-reduced-motion`** | Mengganggu sebagian pengguna | Guard ditambahkan; terverifikasi (`transitionDuration: 0s` dengan emulasi) |
| 8 | **Input di bawah 16px** (select dashboard 0.9rem) | iOS auto-zoom saat fokus → layout pecah | 16px (terverifikasi computed style) |
| 9 | **Empty state tidak konsisten** (hanya teks polos) | Bingung "apakah error atau kosong?" | Ikon + teks + aksi (Reset Filter); teks lama dipertahankan agar aman terhadap test |
| 10 | **Footer © 2025** | Kesan tidak dirawat | © 2026 (3 halaman) |

### Belum dikerjakan — sengaja, butuh keputusan (dicatat sebagai tradeoff)

| # | Temuan | Alasan ditunda |
|---|---|---|
| A | **Format tanggal/angka campur** ("October 2026" vs "15 Oktober 2026"; sumbu chart `35,000,000` vs `Rp 33.000.000`) | Perbaikan menyeluruh = ganti locale global → menyentuh banyak test & format; **butuh sign-off owner** |
| B | **Font pilihan tidak pernah tampil** (Google Fonts diblokir CSP; yang tampil = fallback) | Perlu self-host 3 file font (Inter, Merriweather, Courier Prime) — rekomendasi: lanjutkan di pass `/design typeset` |
| C | **Penolakan pembayaran pakai `prompt()` browser** + aksi verifikasi tidak ada di halaman detail invoice | Perubahan kontrol + aksi = pass `/design interaction` berikutnya |
| D | Loading state pada submit form | Alur postback Django berjalan; dicatat sebagai polish berikutnya |

## 6. Perubahan per File

| File | +/− | Isi perubahan |
|---|---|---|
| `static/css/style.css` | +166 | Blok mobile table-stack; override satu-warna primer; room-tile + reduced-motion |
| `core/templates/core/dashboard.html` | ±33 | KPI tanpa rail; tabel perhatian ber-label; tile pakai CSS (bukan inline JS); select 16px |
| `finance/views.py` | +5/−1 | Konteks `pending_invoice` untuk state portal yang benar |
| `finance/templates/finance/step2_upload.html` | ±11 | Cabang MENUNGGU VERIFIKASI; label file input |
| `finance/templates/finance/invoice_list.html` | ±18 | Kartu mobile + label |
| `finance/templates/finance/ticket_list.html` | ±19 | Kartu mobile + label + ikon empty |
| `finance/templates/finance/operation_list.html` | ±23 | Kartu mobile + label + ikon empty + KPI tanpa rail |
| `finance/templates/finance/report_dashboard.html` | ±6 | KPI tanpa rail |
| `finance/templates/finance/report_form.html` | ±8 | Label a11y |
| `finance/templates/finance/step1_pin.html` | ±8 | Label a11y + © 2026 |
| `finance/templates/finance/success.html` | ±2 | © 2026 |
| `core/templates/core/room_list.html` | ±16 | Kartu mobile + label |
| `tenants/templates/tenants/tenant_list.html` | ±14 | Kartu mobile + label |
| `templates/base.html` | ±2 | Perbaikan item nav aktif |
| `templates/auth/login.html` | ±2 | © 2026 |

Total: **15 file, +246/−87**.

## 7. Verifikasi

| Item | Hasil |
|---|---|
| `manage.py check` | Bersih |
| Full test suite (183 test) | **Exit code 0 (hijau)** — catatan: baris ringkasan stdout tidak tertangkap di mesin ini (keterbatasan lingkungan yang diketahui); verdict diambil dari exit code |
| Render ulang tiap tahap | 1440 & 375, cache-bust; 10 screenshot baru + probe DOM |
| Aksesibilitas | Nama field, `for/id`, reduced-motion, ukuran input — dicek langsung |
| Data | DB development **tidak disentuh**; production **tidak disentuh** |

**Belum diuji (jujur, dicatat):** navigasi keyboard penuh, lebar 320px, zoom 200%, pembaca layar, perangkat fisik, dan performa production.

## 8. Risiko & Catatan

- Perubahan masih **uncommitted** di branch `audit/product-ui-ux` → risiko hilang jika working tree dibersihkan. Rekomendasi: review diff lalu commit terpisah.
- Artefak laporan diagnostik ada di `.commandcode/design/` (checkup/smell/review, md + html). `.commandcode/` sengaja tidak di-commit (berisi state tooling).
- Deployment production **tetap ter-gate** dari fase sebelumnya (akses production belum tersedia) — fase desain ini tidak mengubah status itu.
- Subagent audit tambahan (inventaris antarmuka, penelusuran alur, review adversarial) diluncurkan untuk melengkapi audit, namun hasilnya belum ditarik — audit utama sudah selesai tanpa ketergantungan pada hasil tersebut.

## 9. Rekomendasi Lanjutan (urutan)

1. **Review diff & commit** pekerjaan branch ini (setelah approval owner).
2. **Pass berikutnya (desain):** `/design interaction` (kontrol penolakan + aksi di detail invoice), `/design typeset` (self-host font), lalu refresh checkup.
3. **Keputusan owner:** format locale global (Indonesia) untuk tanggal & angka — perlu dampak-test terpisah.
4. Field-test NYATA: buka di HP staff sungguhan (target utama: alur verifikasi & input listrik dari HP).

---

*Laporan ini disusun dari bukti render, source code, dan hasil test pada branch `audit/product-ui-ux`. Tidak ada klaim perbaikan tanpa verifikasi.*

# Visual Skema Generate Tagihan

## 1) Arsitektur Jalur Generate

```mermaid
flowchart LR
    A[Admin klik Generate Tagihan] --> B[POST /finance/invoice/generate-bulk/]
    B --> C[generate_invoices_bulk]

    D[Cron / Manual Command] --> E[python manage.py generate_monthly_invoices]
    E --> F[Command generate_monthly_invoices]

    C --> G[Logika inti generate]
    F --> G

    G --> H[(Invoice)]
```

## 2) Alur Inti Generate (Business Rules)

```mermaid
flowchart TD
    A[Mulai generate] --> B[Hitung billing_start_base = tanggal 1 bulan depan]
    B --> C[Ambil semua kontrak aktif]
    C --> D{Request dari UI
non-superuser?}

    D -- Ya --> E[Filter kontrak hanya lokasi admin]
    D -- Tidak --> F[Lanjut semua kontrak]
    E --> G[Loop tiap kontrak]
    F --> G

    G --> H{Lokasi mengandung
'ancol'?}

    H -- Ya --> I[Ancol:
billing_start = day dari start_date kontrak]
    I --> J[due_date = billing_start]

    H -- Tidak --> K[Non-Ancol:
billing_start = tanggal 1 bulan depan]
    K --> L[due_date = billing_start + 10 hari]

    J --> M{Invoice periode ini
sudah ada?}
    L --> M

    M -- Belum --> N[Buat Invoice
status BELUM_LUNAS
base_rent = monthly_rent
listrik = 0]
    M -- Sudah --> O[Skip]

    N --> P[Next kontrak]
    O --> P
    P --> Q{Masih ada kontrak?}
    Q -- Ya --> G
    Q -- Tidak --> R[Selesai + tampilkan ringkasan created/skipped]
```

## 3) Sequence Diagram (UI Generate Bulk)

```mermaid
sequenceDiagram
    participant Admin
    participant View as generate_invoices_bulk
    participant Contract as TenantContract
    participant Invoice

    Admin->>View: POST Generate Bulk
    View->>View: Tentukan bulan target (bulan depan)
    View->>Contract: Query kontrak aktif
    View->>View: Filter lokasi jika admin biasa

    loop setiap kontrak aktif
        View->>View: Hitung billing_start & due_date
        View->>Invoice: Cek invoice existing periode tsb
        alt belum ada
            View->>Invoice: Create invoice (BELUM_LUNAS)
        else sudah ada
            View->>View: Skip
        end
    end

    View-->>Admin: Redirect ke invoice list + message hasil
```

## 4) Lifecycle Status Tagihan

```mermaid
stateDiagram-v2
    [*] --> BELUM_LUNAS: Invoice digenerate
    BELUM_LUNAS --> MENUNGGU_VERIFIKASI: Tenant upload bukti bayar
    MENUNGGU_VERIFIKASI --> LUNAS: Admin approve
    MENUNGGU_VERIFIKASI --> BELUM_LUNAS: Admin reject (belum overdue)
    MENUNGGU_VERIFIKASI --> TELAT_BAYAR: Admin reject (sudah overdue)
    BELUM_LUNAS --> TELAT_BAYAR: update_overdue (due_date < today)
```

## 5) Rumus Nilai Tagihan

```mermaid
flowchart LR
    A[base_rent_amount] --> C[total_amount]
    B[electricity_bill_amount] --> C
```

Keterangan:
- total_amount selalu dihitung ulang saat save invoice.
- electricity_bill_amount diupdate dari input meter listrik di detail invoice.

## 6) Catatan Implementasi Penting

- Anti-duplikasi: invoice tidak dibuat jika kontrak + periode billing sudah ada.
- Rule lokasi:
  - Superuser bisa generate semua lokasi.
  - Admin biasa hanya lokasi assignment-nya.
- Perbedaan rule:
  - Ancol = siklus per tenant (mengikuti tanggal mulai kontrak).
  - Non-Ancol = serentak tanggal 1, jatuh tempo H+10.

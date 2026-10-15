# -*- coding: utf-8 -*-
"""
archive.py — KHO LƯU TRỮ BẢN TIN (2 phiên mỗi ngày: SÁNG và CHIỀU)
==================================================================
Mỗi lần chạy (khoảng 7h30 và 16h30), module này:

  1. Chuyển 5 bảng dữ liệu thành tin có cấu trúc.
  2. GỘP vào file của ngày hôm đó:  docs/data/YYYY-MM-DD.json
       - Tin đã có (cùng link, cùng mục) được GIỮ NGUYÊN, không bị ghi đè.
       - Tin mới được thêm vào và gắn nhãn phiên đã phát hiện ra nó ("sang" / "chieu").
       - Tin đã có ở bản sáng nhưng biến mất khỏi nguồn lúc chiều vẫn được giữ lại.
  3. Cập nhật danh mục:  docs/data/index.json
  4. Chép PDF của lần chạy này sang docs/pdf/YYYY-MM-DD-sang.pdf (hoặc ...-chieu.pdf).
     Mỗi ngày có tối đa 2 PDF (sáng, chiều) và TẤT CẢ đều được commit để xem lại về sau.
     Chạy lại cùng một phiên trong ngày sẽ ghi đè PDF của phiên đó.

Quy ước phiên (giờ Việt Nam): trước 12:00 = SÁNG, từ 12:00 = CHIỀU.
Có thể ép phiên bằng biến môi trường PHIEN=sang | chieu (dùng khi chạy thử).

Cách dùng thủ công (ít khi cần):
    python archive.py --rebuild-index     # quét lại docs/data/ và dựng lại index.json
"""

import os
import re
import sys
import json
import shutil

import pandas as pd

GOC = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(GOC, "docs")
DATA_DIR = os.path.join(DOCS_DIR, "data")
PDF_DIR = os.path.join(DOCS_DIR, "pdf")


def _file_pdf(ngay, ed):
    return os.path.join(PDF_DIR, f"{ngay}-{ed}.pdf")

# (id, nhóm, tên hiển thị) — thứ tự này cũng là thứ tự hiển thị trên web
CAC_MUC = [
    ("trong-nuoc", "Trong nước", "Điểm tin vĩ mô & doanh nghiệp"),
    ("cafef", "Trong nước", "Timeline CafeF: nhịp đập thị trường"),
    ("cafebiz", "Trong nước", "Timeline CafeBiz: tin tài chính đã lọc"),
    ("quoc-te", "Quốc tế", "Điểm tin vĩ mô toàn cầu"),
    ("mediastack", "Quốc tế", "Dữ liệu tài chính toàn cầu (Mediastack)"),
]

MOC_CHIEU = 12   # từ 12:00 (giờ VN) trở đi là phiên chiều
TEN_PHIEN = {"sang": "Buổi sáng", "chieu": "Buổi chiều"}
THU_TU_PHIEN = ["sang", "chieu"]

RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ----------------------------------------------------------------------
# Phiên sáng / chiều
# ----------------------------------------------------------------------
def phien_hien_tai(bay_gio=None):
    """Trả về 'sang' hoặc 'chieu' theo giờ Việt Nam (hoặc theo biến môi trường PHIEN nếu có)."""
    ep = os.environ.get("PHIEN", "").strip().lower()
    if ep in TEN_PHIEN:
        return ep
    if bay_gio is None:
        bay_gio = pd.Timestamp.now("Asia/Ho_Chi_Minh")
    return "sang" if bay_gio.hour < MOC_CHIEU else "chieu"


def phien_tu_gio(chuoi):
    """'16:35 ngày 14/10/2026' -> 'chieu'. Dùng cho các file cũ chưa có nhãn phiên."""
    m = re.match(r"\s*(\d{1,2}):\d{2}", chuoi or "")
    if not m:
        return "sang"
    return "chieu" if int(m.group(1)) >= MOC_CHIEU else "sang"


# ----------------------------------------------------------------------
# Làm sạch dữ liệu đầu vào
# ----------------------------------------------------------------------
def _s(giatri):
    """Chuyển bất kỳ giá trị nào (kể cả NaN/None) thành chuỗi sạch."""
    if giatri is None:
        return ""
    try:
        if pd.isna(giatri):
            return ""
    except (TypeError, ValueError):
        pass
    return str(giatri).strip()


def _dau_tien(row, cac_cot):
    """Lấy giá trị đầu tiên không rỗng trong danh sách tên cột (mỗi nguồn đặt tên cột khác nhau)."""
    for cot in cac_cot:
        v = _s(row.get(cot))
        if v:
            return v
    return ""


def _chuan_hoa(df, cot_tieu_de, cot_tom_tat, tach_nguon=False, nguon_mac_dinh=""):
    """Đưa 1 bảng (DataFrame) về danh sách tin có cấu trúc thống nhất."""
    if df is None or len(df) == 0:
        return []
    ket_qua = []
    for _, row in df.iterrows():
        tieu_de = _dau_tien(row, cot_tieu_de)
        if not tieu_de:
            continue
        nguon = nguon_mac_dinh
        # Tin RSS của Google News có dạng "Tiêu đề - Tên báo": tách tên báo ra riêng
        if tach_nguon and " - " in tieu_de:
            phan_dau, phan_cuoi = tieu_de.rsplit(" - ", 1)
            tieu_de, nguon = phan_dau.strip(), phan_cuoi.strip()
        ket_qua.append(
            {
                "time": _s(row.get("Thời gian")),
                "category": _s(row.get("Chuyên mục")),
                "title": tieu_de,
                "source": nguon,
                "summary": _dau_tien(row, cot_tom_tat),
                "link": _s(row.get("Link")),
            }
        )
    return ket_qua


# ----------------------------------------------------------------------
# Gộp tin giữa các lần chạy trong ngày
# ----------------------------------------------------------------------
def _tom_tat_yeu(s):
    """Tóm tắt rỗng hoặc là câu báo lỗi / 'không đủ dữ liệu' của lần gọi Gemini."""
    s = (s or "").strip().lower()
    if not s or s.startswith("lỗi") or "không thể dịch" in s:
        return True
    return len(s) < 90 and "không đủ" in s


def _khoa_tin(it):
    """Khóa nhận diện 1 tin: ưu tiên link, nếu không có thì dùng tiêu đề."""
    link = (it.get("link") or "").strip()
    if link and link != "#":
        return ("l", link)
    return ("t", " ".join((it.get("title") or "").lower().split()))


def chuan_hoa_ngay_cu(goi):
    """File ngày do phiên bản cũ tạo (chưa có nhãn phiên): suy ra phiên từ giờ tổng hợp.
    Trả về chính đối tượng đã được bổ sung 'editions' và 'ed' cho từng tin."""
    if not goi:
        return goi
    if not goi.get("editions"):
        ed = phien_tu_gio(goi.get("generated_at", ""))
        goi["editions"] = {ed: {"generated_at": goi.get("generated_at", "")}}
    mac_dinh = next(iter(goi["editions"]))
    for muc in goi.get("sections", []):
        for it in muc.get("items", []):
            if it.get("ed") not in TEN_PHIEN:
                it["ed"] = mac_dinh
    return goi


def gop_ban_tin(cu, moi_theo_muc, ed, gio_hien_thi, ngay):
    """Gộp tin mới của phiên `ed` vào dữ liệu đã có của ngày (cu có thể là None).
    Không bao giờ làm mất tin đã lưu."""
    cu = chuan_hoa_ngay_cu(cu) or {}
    cu_theo_muc = {m["id"]: m.get("items", []) for m in cu.get("sections", [])}

    cac_muc = []
    for id_muc, nhom, ten in CAC_MUC:
        da_co = cu_theo_muc.get(id_muc, [])
        chi_muc = {_khoa_tin(it): it for it in da_co}
        them = []
        for it in moi_theo_muc.get(id_muc, []):
            k = _khoa_tin(it)
            ex = chi_muc.get(k)
            if ex is not None:
                # Tin đã có: giữ nguyên nhãn phiên đầu tiên; chỉ bổ sung chỗ còn thiếu
                if _tom_tat_yeu(ex.get("summary")) and not _tom_tat_yeu(it.get("summary")):
                    ex["summary"] = it["summary"]
                for f in ("time", "category", "source", "link"):
                    if not ex.get(f) and it.get(f):
                        ex[f] = it[f]
            else:
                moi = dict(it)
                moi["ed"] = ed
                them.append(moi)
                chi_muc[k] = moi
        items = them + da_co          # tin mới nhất xếp trước
        if items:
            cac_muc.append({"id": id_muc, "group": nhom, "title": ten, "items": items})

    editions = dict(cu.get("editions", {}))
    editions[ed] = {"generated_at": gio_hien_thi}
    return {"date": ngay, "generated_at": gio_hien_thi, "editions": editions, "sections": cac_muc}


def _migrar_pdf_cu(ngay, goi):
    """PDF kiểu cũ (docs/pdf/YYYY-MM-DD.pdf, mỗi ngày 1 file) -> kiểu mới theo phiên.
    Chỉ áp dụng cho ngày do phiên bản cũ tạo (file ngày chưa có 'editions'). Đổi tên = giữ nguyên nội dung,
    git nhận ra là đổi tên nên không tốn thêm dung lượng."""
    if not goi or goi.get("editions"):
        return
    cu = os.path.join(PDF_DIR, f"{ngay}.pdf")
    if not os.path.exists(cu):
        return
    ed0 = phien_tu_gio(goi.get("generated_at", ""))
    moi = _file_pdf(ngay, ed0)
    if os.path.exists(moi):
        return
    os.replace(cu, moi)
    print(f"  -> Đổi tên PDF cũ {os.path.basename(cu)} -> {os.path.basename(moi)}")


# ----------------------------------------------------------------------
# Đọc / ghi file
# ----------------------------------------------------------------------
def _doc_json(duong_dan, mac_dinh):
    if not os.path.exists(duong_dan):
        return mac_dinh
    try:
        with open(duong_dan, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  ⚠️ Không đọc được {duong_dan}: {e}")
        return mac_dinh


def _ghi_json(duong_dan, du_lieu):
    os.makedirs(os.path.dirname(duong_dan), exist_ok=True)
    tam = duong_dan + ".tmp"
    with open(tam, "w", encoding="utf-8") as f:
        json.dump(du_lieu, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tam, duong_dan)  # ghi nguyên tử: không bao giờ để lại file dở dang


def xay_lai_index():
    """Quét docs/data/ và docs/pdf/ rồi dựng lại index.json (kèm danh sách PDF của từng ngày)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    duong_dan_index = os.path.join(DATA_DIR, "index.json")

    cac_ngay = []
    for ten in sorted(os.listdir(DATA_DIR)):
        ngay = ten[:-5]
        if not ten.endswith(".json") or not RE_NGAY.match(ngay):
            continue
        goi = _doc_json(os.path.join(DATA_DIR, ten), None)
        if not goi:
            continue
        _migrar_pdf_cu(ngay, goi)
        so_tin = sum(len(m.get("items", [])) for m in goi.get("sections", []))
        eds = list((goi.get("editions") or {}).keys()) or [phien_tu_gio(goi.get("generated_at", ""))]
        pdfs = {e: f"pdf/{ngay}-{e}.pdf" for e in THU_TU_PHIEN if os.path.exists(_file_pdf(ngay, e))}
        cac_ngay.append(
            {
                "date": ngay,
                "count": so_tin,
                "editions": [e for e in THU_TU_PHIEN if e in eds],
                "generated": goi.get("generated_at", ""),
                "pdfs": pdfs,
            }
        )
    cac_ngay.sort(key=lambda d: d["date"], reverse=True)
    _ghi_json(duong_dan_index, {"days": cac_ngay})
    print(f"  -> index.json: {len(cac_ngay)} ngày.")
    return cac_ngay


def luu_ban_tin(
    df_trong_nuoc,
    df_cafef,
    df_cafebiz,
    df_quoc_te,
    df_mediastack,
    duong_dan_pdf=None,
    gio_hien_thi="",
    ngay=None,
    phien=None,
):
    """Gộp bản tin của lần chạy này vào file của ngày. Trả về đường dẫn file JSON,
    hoặc None nếu lần chạy này không có tin nào (khi đó không đụng gì tới kho)."""
    if ngay is None:
        ngay = pd.Timestamp.now("Asia/Ho_Chi_Minh").strftime("%Y-%m-%d")
    if not RE_NGAY.match(ngay):
        raise ValueError(f"Ngày không hợp lệ: {ngay!r} (cần dạng YYYY-MM-DD)")
    ed = phien if phien in TEN_PHIEN else phien_hien_tai()

    print(f"\n[Kho lưu trữ] Đang gộp bản tin {TEN_PHIEN[ed].lower()} ngày {ngay}...")

    moi_theo_muc = {
        "trong-nuoc": _chuan_hoa(df_trong_nuoc, ["Tiêu đề gốc", "Tiêu đề"],
                                 ["Tóm tắt AI (Đã xác minh)", "Tóm tắt AI"], tach_nguon=True),
        "cafef": _chuan_hoa(df_cafef, ["Tiêu đề", "Tiêu đề Bài báo"],
                            ["Tóm tắt AI"], nguon_mac_dinh="CafeF"),
        "cafebiz": _chuan_hoa(df_cafebiz, ["Tiêu đề", "Tiêu đề bài báo"],
                              ["Tóm tắt AI"], nguon_mac_dinh="CafeBiz"),
        "quoc-te": _chuan_hoa(df_quoc_te, ["Tiêu đề gốc", "Tiêu đề"],
                              ["Tóm tắt AI (Đã xác minh)", "Tóm tắt AI"], tach_nguon=True),
        "mediastack": _chuan_hoa(df_mediastack, ["Tiêu đề bài báo", "Tiêu đề Gốc"],
                                 ["Tóm tắt AI"], nguon_mac_dinh="Mediastack"),
    }
    if sum(len(v) for v in moi_theo_muc.values()) == 0:
        print("  ⚠️ Lần chạy này không có tin nào -> KHÔNG thay đổi kho lưu trữ.")
        return None

    duong_dan_json = os.path.join(DATA_DIR, f"{ngay}.json")
    cu = _doc_json(duong_dan_json, None)
    _migrar_pdf_cu(ngay, cu)          # trước khi gộp: file cũ còn nguyên dấu hiệu "chưa có editions"
    truoc = sum(len(m.get("items", [])) for m in (cu or {}).get("sections", []))

    goi = gop_ban_tin(cu, moi_theo_muc, ed, gio_hien_thi, ngay)
    sau = sum(len(m["items"]) for m in goi["sections"])
    _ghi_json(duong_dan_json, goi)
    print(f"  -> {duong_dan_json}: {truoc} tin cũ + {sau - truoc} tin mới = {sau} tin.")

    # PDF của lần chạy này: giữ lại vĩnh viễn, mỗi phiên một file
    if duong_dan_pdf and os.path.exists(duong_dan_pdf):
        os.makedirs(PDF_DIR, exist_ok=True)
        shutil.copyfile(duong_dan_pdf, _file_pdf(ngay, ed))
        print(f"  -> PDF: {_file_pdf(ngay, ed)}")

    xay_lai_index()
    return duong_dan_json


if __name__ == "__main__":
    if "--rebuild-index" in sys.argv:
        xay_lai_index()
    else:
        print(__doc__)

# -*- coding: utf-8 -*-
"""
archive.py — KHO LƯU TRỮ BẢN TIN
================================
Mỗi ngày, sau khi lấy tin + tóm tắt AI xong, module này chuyển 5 bảng dữ liệu
thành 1 file JSON duy nhất:  docs/data/YYYY-MM-DD.json
và cập nhật danh mục:        docs/data/index.json
(đồng thời sao chép PDF của ngày đó vào docs/pdf/YYYY-MM-DD.pdf).

Trang web trong thư mục docs/ (GitHub Pages) chỉ việc đọc các file JSON này để
hiển thị theo ngày và tìm kiếm từ khóa trên toàn bộ lịch sử.

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

# (id, nhóm, tên hiển thị) — thứ tự này cũng là thứ tự hiển thị trên web
CAC_MUC = [
    ("trong-nuoc", "Trong nước", "Điểm tin vĩ mô & doanh nghiệp"),
    ("cafef", "Trong nước", "Timeline CafeF: nhịp đập thị trường"),
    ("cafebiz", "Trong nước", "Timeline CafeBiz: tin tài chính đã lọc"),
    ("quoc-te", "Quốc tế", "Điểm tin vĩ mô toàn cầu"),
    ("mediastack", "Quốc tế", "Dữ liệu tài chính toàn cầu (Mediastack)"),
]

RE_NGAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    """Lấy giá trị đầu tiên không rỗng trong danh sách tên cột (vì mỗi nguồn đặt tên cột khác nhau)."""
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
    """Quét thư mục docs/data/ và dựng lại index.json (dùng sau khi nhập dữ liệu lịch sử)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    cac_ngay = []
    for ten in sorted(os.listdir(DATA_DIR)):
        ngay = ten[:-5]
        if not ten.endswith(".json") or not RE_NGAY.match(ngay):
            continue
        goi = _doc_json(os.path.join(DATA_DIR, ten), None)
        if not goi:
            continue
        so_tin = sum(len(m.get("items", [])) for m in goi.get("sections", []))
        cac_ngay.append(
            {
                "date": ngay,
                "count": so_tin,
                "pdf": os.path.exists(os.path.join(PDF_DIR, f"{ngay}.pdf")),
                "generated": goi.get("generated_at", ""),
            }
        )
    cac_ngay.sort(key=lambda d: d["date"], reverse=True)
    _ghi_json(os.path.join(DATA_DIR, "index.json"), {"days": cac_ngay})
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
):
    """Lưu bản tin của 1 ngày. Trả về đường dẫn file JSON, hoặc None nếu hôm nay không có tin nào."""
    if ngay is None:
        ngay = pd.Timestamp.now("Asia/Ho_Chi_Minh").strftime("%Y-%m-%d")
    if not RE_NGAY.match(ngay):
        raise ValueError(f"Ngày không hợp lệ: {ngay!r} (cần dạng YYYY-MM-DD)")

    print(f"\n[Kho lưu trữ] Đang lưu bản tin ngày {ngay}...")

    cac_bang = {
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

    cac_muc = []
    for id_muc, nhom, ten in CAC_MUC:
        if cac_bang[id_muc]:
            cac_muc.append({"id": id_muc, "group": nhom, "title": ten, "items": cac_bang[id_muc]})

    tong = sum(len(m["items"]) for m in cac_muc)
    if tong == 0:
        print("  ⚠️ Hôm nay không có tin nào -> KHÔNG ghi đè kho lưu trữ.")
        return None

    goi = {"date": ngay, "generated_at": gio_hien_thi, "sections": cac_muc}

    # Sao chép PDF của ngày (nếu có) để trang web có nút "Tải PDF"
    if duong_dan_pdf and os.path.exists(duong_dan_pdf):
        os.makedirs(PDF_DIR, exist_ok=True)
        shutil.copyfile(duong_dan_pdf, os.path.join(PDF_DIR, f"{ngay}.pdf"))
        goi["pdf"] = f"pdf/{ngay}.pdf"

    duong_dan_json = os.path.join(DATA_DIR, f"{ngay}.json")
    _ghi_json(duong_dan_json, goi)
    print(f"  -> Đã lưu {tong} tin vào {duong_dan_json}")

    xay_lai_index()
    return duong_dan_json


if __name__ == "__main__":
    if "--rebuild-index" in sys.argv:
        xay_lai_index()
    else:
        print(__doc__)

# -*- coding: utf-8 -*-
"""
dich_bu.py — DỊCH BÙ TIẾNG ANH CHO TIN CŨ (chạy một lần bằng workflow "Dich bu tieng Anh")
=========================================================================================
Mỗi lần chạy hằng ngày chỉ dịch tối đa 200 tin (ưu tiên tin mới nhất), nên kho tin cũ được dịch dần.
Script này dịch nhiều tin hơn trong một lần để đuổi kịp: không lấy tin mới, không tạo bản tin mới, chỉ bổ sung
"title_en"/"summary_en" vào các file docs/data/*.json còn thiếu. Chạy lại bao nhiêu lần cũng an toàn.

Biến môi trường:
    GEMINI_API_KEY   (bắt buộc)
    TOI_DA           số tin tối đa dịch trong lần này (mặc định 800)
    GIOI_HAN_GIAY    ngân sách thời gian cho bước dịch, tính bằng giây (mặc định 1800)
"""

import os
import sys


def _so_nguyen(ten, mac_dinh, nho_nhat, lon_nhat):
    """Đọc số nguyên từ biến môi trường; sai định dạng thì dùng mặc định, ngoài khoảng thì kẹp lại."""
    try:
        v = int(str(os.environ.get(ten, "")).strip())
    except ValueError:
        v = mac_dinh
    return max(nho_nhat, min(lon_nhat, v))


def chay(goi_gemini, toi_da, gioi_han_giay, thu_muc=None):
    """Dịch bù và trả về (thống kê, mã thoát). Mã thoát 1 khi còn tin cần dịch mà không dịch được tin nào
    (API hỏng/hết hạn mức) để GitHub báo đỏ thay vì im lặng."""
    from translate_en import dich_kho_luu_tru

    st = dich_kho_luu_tru(
        goi_gemini, toi_da=toi_da, gioi_han_giay=gioi_han_giay, thu_muc=thu_muc, toi_da_loi_lien_tiep=3
    )
    print(
        f"\nKẾT QUẢ DỊCH BÙ: vừa dịch {st['da_dich']} tin, còn {st['con_lai']} tin chưa dịch"
        + (" -> chạy lại workflow để dịch tiếp." if st["con_lai"] else " -> ĐÃ DỊCH HẾT.")
    )
    if st["da_dich"] == 0 and st["con_lai"] > 0:
        print("❌ Không dịch được tin nào (Gemini lỗi hoặc hết hạn mức). Thử lại sau.")
        return st, 1
    return st, 0


if __name__ == "__main__":
    from main import goi_gemini     # dùng đúng hàm gọi Gemini (có thử lại) của quy trình chính

    _, ma = chay(goi_gemini, _so_nguyen("TOI_DA", 800, 1, 5000), _so_nguyen("GIOI_HAN_GIAY", 1800, 60, 3000))
    sys.exit(ma)

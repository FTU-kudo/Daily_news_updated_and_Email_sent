# -*- coding: utf-8 -*-
"""
BÁO CÁO TIN TỨC THỊ TRƯỜNG HÀNG NGÀY — PHIÊN BẢN TỰ ĐỘNG HÓA
=============================================================
Chuyển thể từ notebook Colab gốc, loại bỏ mọi phụ thuộc vào Colab
(google.colab.userdata, google.colab.drive) để có thể chạy "không người
giám sát" trên GitHub Actions (hoặc bất kỳ máy chủ Linux nào khác).

Luồng xử lý:
  1. Lấy tin trong nước (Google News RSS)        -> tom_tat bằng Gemini
  2. Lấy tin quốc tế (Google News RSS)            -> tom_tat bằng Gemini
  3. Cào tin CafeF + CafeBiz                      -> tom_tat bằng Gemini
  4. Lấy tin Mediastack                           -> dịch + tom_tat bằng Gemini
  5. Dựng báo cáo HTML -> xuất PDF (WeasyPrint)
  6. Upload PDF lên Google Drive (Service Account)
  7. Gửi email kèm PDF đến danh sách khách hàng (Gmail SMTP)

Toàn bộ thông tin nhạy cảm (API key, mật khẩu...) được đọc từ biến môi
trường, không hard-code trong code, để có thể lưu an toàn trong
GitHub Secrets.
"""

import os
import io
import sys
import json
import time
import smtplib
import mimetypes
import argparse
from email.message import EmailMessage

import requests
import feedparser
import pandas as pd
from bs4 import BeautifulSoup

from google import genai
from google.genai import types
from google.genai.errors import APIError


# ======================================================================
# 0. CẤU HÌNH CHUNG
# ======================================================================
WORKDIR = os.path.dirname(os.path.abspath(__file__))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MEDIA_STACK_KEY = os.environ.get("MEDIA_STACK_API_KEY", "")
TEN_MODEL = "gemini-3.1-flash-lite"

if not GEMINI_API_KEY:
    sys.exit("❌ Thiếu biến môi trường GEMINI_API_KEY. Hãy khai báo secret trước khi chạy.")

client = genai.Client(api_key=GEMINI_API_KEY)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def goi_gemini(prompt_text, retries=3, wait_giay=20):
    """Gọi Gemini, tự động thử lại khi gặp lỗi quota/mạng. Trả về dict JSON hoặc None."""
    for lan in range(retries):
        try:
            response = client.models.generate_content(
                model=TEN_MODEL,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                            threshold=types.HarmBlockThreshold.BLOCK_NONE,
                        ),
                    ],
                ),
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()
            obj, _ = json.JSONDecoder().raw_decode(raw_text)
            return obj
        except APIError as e:
            print(f"  ⚠️ Lỗi máy chủ Gemini (lần {lan + 1}/{retries}): {e}")
            time.sleep(wait_giay)
        except Exception as e:
            msg = str(e)
            if "429" in msg or "Quota" in msg:
                print(f"  ⚠️ Quá tải định mức API (lần {lan + 1}/{retries}). Chờ {wait_giay}s...")
                time.sleep(wait_giay)
            else:
                print(f"  ❌ Lỗi xử lý: {e}")
                time.sleep(3)
    return None


# ======================================================================
# 1. TIN TRONG NƯỚC (Google News RSS)
# ======================================================================
def lay_tin_trong_nuoc():
    print("\n[1/5] Đang lấy tin trong nước (Google News RSS)...")
    nguon = {
        "Kinh tế Vĩ mô": "https://news.google.com/rss/search?q=(kinh+tế+OR+tài+chính+OR+ngân+hàng)+when:24h&hl=vi&gl=VN&ceid=VN:vi",
        "Tin Thời sự": "https://news.google.com/rss?hl=vi&gl=VN&ceid=VN:vi",
        "Tin Cập nhật": "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FuWnBHZ0pXVGlnQVAB?hl=vi&gl=VN&ceid=VN:vi",
    }

    danh_sach_tin = []
    id_counter = 0
    for chuyen_muc, url in nguon.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            try:
                thoi_gian_goc = pd.to_datetime(entry.published, utc=True)
                thoi_gian_str = thoi_gian_goc.tz_convert("Asia/Ho_Chi_Minh").strftime("%d/%m/%Y %H:%M")
            except Exception:
                thoi_gian_str = ""
            mo_ta_goc = BeautifulSoup(entry.get("summary", ""), "html.parser").text.strip()
            danh_sach_tin.append(
                {
                    "ID": id_counter,
                    "Chuyên mục": chuyen_muc,
                    "Tiêu đề gốc": entry.title,
                    "Mô tả gốc": mo_ta_goc,
                    "Link": entry.link,
                    "Thời gian": thoi_gian_str,
                }
            )
            id_counter += 1
        time.sleep(0.3)

    print(f"  -> Thu thập {len(danh_sach_tin)} tin trong nước.")
    if not danh_sach_tin:
        return pd.DataFrame()

    prompt = (
        "Bạn là Giám đốc Phân tích Đầu tư tại thị trường Việt Nam.\n"
        "Dưới đây là danh sách bài báo vĩ mô và doanh nghiệp. Mỗi bài có một ID riêng.\n\n"
        "HÃY TUÂN THỦ TUYỆT ĐỐI CÁC NGUYÊN TẮC SAU ĐỂ ĐẢM BẢO CHẤT LƯỢNG BÁO CÁO:\n"
        "1. CHỈ phân tích dựa trên thông tin được cung cấp. Tuyệt đối KHÔNG tự bịa đặt số liệu hoặc diễn biến nằm ngoài văn bản (Hallucination).\n"
        "2. Viết một đoạn 'Market Insight' (3-4 câu) bằng tiếng Việt tổng hợp bức tranh vĩ mô, đánh giá rủi ro/cơ hội đến chỉ số VN-Index, nhóm ngành ngân hàng hoặc năng lượng. Nội dung phải được cập nhật mới nhất, tính đến ngày hôm nay.\n"
        "3. Với mỗi bài báo, viết một đoạn tóm tắt ngắn gọn, cô đọng (2-3 câu) bằng tiếng Việt giải thích rõ bản chất sự kiện.\n"
        "4. QUAN TRỌNG: Với các bản tin mà 'Mô tả gốc' bị lặp lại tiêu đề hoặc trống rỗng (thường gặp ở luồng Kinh tế Vĩ mô dạng tìm kiếm), BẠN ĐƯỢC PHÉP phân tích ý nghĩa và bối cảnh kinh tế của sự kiện đó dựa trên 'Tiêu đề gốc'. Chỉ khi tiêu đề cũng vô nghĩa, mới ghi 'Không đủ dữ liệu tóm tắt.'\n\n"
        "5. CẬP NHẬT BỐI CẢNH THỰC TẾ: Tuyệt đối không được gọi Donald Trump là 'cựu Tổng thống'. Bắt buộc phải sử dụng đúng danh xưng là 'Tổng thống Trump' hoặc 'Ông Trump' trong mọi bản tóm tắt.\n\n"
    )
    for tin in danh_sach_tin:
        prompt += f"ID: {tin['ID']}\nTiêu đề: {tin['Tiêu đề gốc']}\nMô tả gốc: {tin['Mô tả gốc']}\n\n"
    prompt += """
TRẢ VỀ KẾT QUẢ BẮT BUỘC THEO ĐÚNG CẤU TRÚC JSON SAU (không chứa ký tự markdown):
{
  "insight": "Đoạn đánh giá tổng quan thị trường bằng tiếng Việt...",
  "ket_qua": [
    {"id": 0, "tom_tat": "Tóm tắt bài số 0 bằng tiếng Việt (2-3 câu)..."}
  ]
}
"""
    ket_qua_json = goi_gemini(prompt)
    if ket_qua_json and "ket_qua" in ket_qua_json:
        map_tom_tat = {item["id"]: item["tom_tat"] for item in ket_qua_json["ket_qua"]}
        for tin in danh_sach_tin:
            tin["Tóm tắt AI (Đã xác minh)"] = map_tom_tat.get(
                tin["ID"], "Thông tin gốc không đủ cơ sở dữ liệu để tiến hành tóm tắt."
            )
    else:
        for tin in danh_sach_tin:
            tin["Tóm tắt AI (Đã xác minh)"] = "Lỗi kết nối và xử lý dữ liệu từ API."

    df = pd.DataFrame(danh_sach_tin).drop(columns=["Mô tả gốc", "ID"])
    duong_dan = os.path.join(WORKDIR, "tin_trong_nuoc_rss_chuan.csv")
    df.to_csv(duong_dan, index=False, sep=";", encoding="utf-8-sig")
    print(f"  -> Đã lưu {duong_dan}")
    return df


# ======================================================================
# 2. TIN QUỐC TẾ (Google News RSS)
# ======================================================================
def lay_tin_quoc_te():
    print("\n[2/5] Đang lấy tin quốc tế (Google News RSS)...")
    nguon = {
        "Tin Nổi Bật Toàn Cầu": "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
        "Doanh Nghiệp Quốc Tế": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
        "Vĩ Mô & Phố Wall": "https://news.google.com/rss/search?q=(finance+OR+economy+OR+wall+street)+when:24h&hl=en-US&gl=US&ceid=US:en",
    }

    danh_sach_tin = []
    id_counter = 0
    for chuyen_muc, url in nguon.items():
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            try:
                thoi_gian_goc = pd.to_datetime(entry.published, utc=True)
                thoi_gian_str = thoi_gian_goc.tz_convert("Asia/Ho_Chi_Minh").strftime("%d/%m/%Y %H:%M")
            except Exception:
                thoi_gian_str = ""
            mo_ta_goc = BeautifulSoup(entry.get("summary", ""), "html.parser").text.strip()
            danh_sach_tin.append(
                {
                    "ID": id_counter,
                    "Chuyên mục": chuyen_muc,
                    "Tiêu đề gốc": entry.title,
                    "Mô tả gốc": mo_ta_goc,
                    "Link": entry.link,
                    "Thời gian": thoi_gian_str,
                }
            )
            id_counter += 1
        time.sleep(0.3)

    print(f"  -> Thu thập {len(danh_sach_tin)} tin quốc tế.")
    if not danh_sach_tin:
        return pd.DataFrame()

    prompt = (
        "Bạn là Giám đốc Phân tích Vĩ mô Toàn cầu và là một biên dịch viên kinh tế chuyên nghiệp.\n"
        "Dưới đây là danh sách tiêu đề và mô tả tin tức quốc tế bằng tiếng Anh. Mỗi bài có một ID riêng.\n\n"
        "HÃY TUÂN THỦ CÁC NGUYÊN TẮC SAU:\n"
        "1. Viết một đoạn 'Market Insight' (3-4 câu) bằng tiếng Việt tổng hợp xu hướng dòng vốn, chính sách tiền tệ hoặc biến động thị trường.\n"
        "2. Với mỗi bài báo, viết một đoạn tóm tắt ngắn gọn, cô đọng (2-3 câu) bằng tiếng Việt.\n"
        "3. QUAN TRỌNG: Với các bản tin mà 'Mô tả gốc' bị lặp lại tiêu đề hoặc không có nội dung, BẠN ĐƯỢC PHÉP phân tích ý nghĩa và bối cảnh tài chính của sự kiện đó dựa trên 'Tiêu đề gốc'. Chỉ khi tiêu đề cũng vô nghĩa, mới ghi 'Không đủ dữ liệu tóm tắt.'\n\n"
        "4. Nếu nội dung báo lỗi, ghi: 'Không đủ dữ liệu bài viết để phân tích.'\n"
        "5. CẬP NHẬT BỐI CẢNH THỰC TẾ: Tuyệt đối không được gọi Donald Trump là 'cựu Tổng thống'. Bắt buộc phải sử dụng đúng danh xưng là 'Tổng thống Trump' hoặc 'Ông Trump' trong mọi bản tóm tắt.\n\n"
    )
    for tin in danh_sach_tin:
        prompt += f"ID: {tin['ID']}\nTiêu đề: {tin['Tiêu đề gốc']}\nMô tả gốc: {tin['Mô tả gốc']}\n\n"
    prompt += """
TRẢ VỀ KẾT QUẢ BẮT BUỘC THEO ĐÚNG CẤU TRÚC JSON SAU:
{
  "insight": "Đoạn đánh giá vĩ mô toàn cầu...",
  "ket_qua": [
    {"id": 0, "tom_tat": "Tóm tắt bài số 0 (2-3 câu)..."}
  ]
}
"""
    ket_qua_json = goi_gemini(prompt)
    if ket_qua_json and "ket_qua" in ket_qua_json:
        map_tom_tat = {item["id"]: item["tom_tat"] for item in ket_qua_json["ket_qua"]}
        for tin in danh_sach_tin:
            tin["Tóm tắt AI"] = map_tom_tat.get(tin["ID"], "Thông tin gốc từ RSS không đủ cơ sở để tóm tắt.")
    else:
        for tin in danh_sach_tin:
            tin["Tóm tắt AI"] = "Lỗi kết nối và xử lý dữ liệu từ API."

    df = pd.DataFrame(danh_sach_tin).drop(columns=["Mô tả gốc", "ID"])
    duong_dan = os.path.join(WORKDIR, "tin_quoc_te_rss_chuan.csv")
    df.to_csv(duong_dan, index=False, sep=";", encoding="utf-8-sig")
    print(f"  -> Đã lưu {duong_dan}")
    return df


# ======================================================================
# 3. CAFEF + CAFEBIZ (Cào dữ liệu trực tiếp)
# ======================================================================
def lay_tin_cafef(so_luong=8):
    url = "https://cafef.vn/thi-truong-chung-khoan.chn"
    print("\n[3/5] Đang quét CafeF (Thị trường Chứng khoán)...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  ❌ Lỗi kết nối CafeF: {e}")
        return pd.DataFrame()

    items = soup.find_all("div", attrs={"role": "article", "class": lambda c: c and "tlitem" in c})

    danh_sach_tin = []
    for idx, item in enumerate(items[:so_luong]):
        h3 = item.find("h3")
        if not h3 or not h3.find("a"):
            continue
        a_tag = h3.find("a")
        tieu_de = a_tag.get("title", a_tag.text).strip()
        link = a_tag["href"]
        if link.startswith("/"):
            link = "https://cafef.vn" + link

        time_span = item.find("span", class_="time-ago") or item.find("span", class_="time")
        thoi_gian_iso = time_span.get("title", "") if time_span else ""
        try:
            thoi_gian_str = pd.to_datetime(thoi_gian_iso).strftime("%d/%m/%Y %H:%M") if thoi_gian_iso else ""
        except Exception:
            thoi_gian_str = thoi_gian_iso

        sapo_tag = item.find("p", class_=lambda c: c and "sapo" in c)
        sapo = sapo_tag.text.strip() if sapo_tag else ""

        danh_sach_tin.append(
            {
                "ID": idx,
                "Nguon": "CafeF",
                "Thời gian": thoi_gian_str,
                "Tiêu đề": tieu_de,
                "Mô tả gốc": sapo,
                "Link": link,
            }
        )

    print(f"  -> Lấy được {len(danh_sach_tin)} bài CafeF.")
    return pd.DataFrame(danh_sach_tin)


def lay_tin_cafebiz(so_luong=8, chuyen_muc_loc=("Kinh doanh", "Tài chính ngân hàng", "Chứng khoán", "Bất động sản", "Doanh nghiệp", "Tiền tệ", "Lãi suất", "Công ty", "Cổ phiếu")):
    url = "https://cafebiz.vn/"
    print("  Đang quét CafeBiz (Trang chủ, lọc chuyên mục Kinh doanh)...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  ❌ Lỗi kết nối CafeBiz: {e}")
        return pd.DataFrame()

    stream_container = soup.find("ul", class_=lambda c: c and "list_cfbiznews-mid" in c)
    if not stream_container:
        print("  ⚠️ Không tìm thấy luồng tin trang chủ.")
        return pd.DataFrame()

    list_items = stream_container.find_all("li", class_="item")

    danh_sach_tin = []
    seen_links = set()
    idx = 0

    for li in list_items:
        art = li.find("article", class_=lambda c: c and "cfbiznews_box" in c)
        if not art:
            continue

        cate_tag = art.find("a", class_=lambda c: c and "cfbiznews-type" in c)
        chuyen_muc = cate_tag.text.strip() if cate_tag else ""

        if chuyen_muc_loc and not any(kw in chuyen_muc for kw in chuyen_muc_loc):
            continue

        title_tag = art.find("a", class_=lambda c: c and "cfbiznews_title" in c)
        if not title_tag or not title_tag.get("href"):
            continue

        link = title_tag["href"]
        if link.startswith("/"):
            link = "https://cafebiz.vn" + link
        if link in seen_links:
            continue
        seen_links.add(link)

        tieu_de = title_tag.get("title", title_tag.text).strip()

        time_tag = art.find(class_=lambda c: c and "time-ago" in c)
        thoi_gian_str = ""
        if time_tag:
            raw_time = time_tag.get("title", "").strip() or time_tag.text.strip()
            try:
                thoi_gian_str = pd.to_datetime(raw_time).strftime("%d/%m/%Y %H:%M")
            except Exception:
                thoi_gian_str = time_tag.text.strip()

        sapo_tag = art.find(class_=lambda c: c and "cfbiznews_sapo" in c)
        sapo = sapo_tag.text.strip() if sapo_tag else ""

        danh_sach_tin.append(
            {
                "ID": idx,
                "Nguon": "CafeBiz",
                "Thời gian": thoi_gian_str,
                "Chuyên mục": chuyen_muc,
                "Tiêu đề": tieu_de,
                "Mô tả gốc": sapo,
                "Link": link,
            }
        )

        idx += 1
        if idx >= so_luong:
            break

    co_thoi_gian = sum(1 for t in danh_sach_tin if t["Thời gian"])
    print(f"  -> Lấy được {len(danh_sach_tin)} bài thuộc {chuyen_muc_loc} "
          f"({co_thoi_gian} bài có ngày giờ).")

    if not danh_sach_tin:
        print("  ⚠️ Không có bài nào khớp chuyên mục lọc trong luồng tin hiện tại. "
              "Thử tăng so_luong hoặc nới rộng chuyen_muc_loc.")

    return pd.DataFrame(danh_sach_tin)

def tom_tat_voi_ai(df, ten_nguon):
    if df.empty:
        return df

    prompt = (
        "Bạn là chuyên gia phân tích thị trường tài chính Việt Nam.\n"
        f"Dưới đây là danh sách bài báo từ {ten_nguon}. Mỗi bài có ID riêng.\n\n"
        "QUY TẮC:\n"
        "1. CHỈ tóm tắt dựa trên 'Mô tả gốc'. KHÔNG bịa thêm số liệu hay chi tiết không có trong dữ liệu.\n"
        "2. NẾU 'Mô tả gốc' để trống, chỉ được diễn giải lại ý nghĩa của 'Tiêu đề' — "
        "không suy đoán thêm tình tiết cụ thể (số liệu, tên người, nguyên nhân...) ngoài tiêu đề.\n"
        "3. Viết tóm tắt ngắn gọn (1-2 câu nếu chỉ có tiêu đề, 2-3 câu nếu có mô tả) bằng tiếng Việt.\n"
        "4. Viết 1 đoạn 'insight' (3-4 câu) tổng hợp xu hướng chung của các bài.\n\n"
    )
    for _, row in df.iterrows():
        mo_ta = row.get("Mô tả gốc", "") or "(không có mô tả, chỉ có tiêu đề)"
        prompt += f"ID: {row['ID']}\nTiêu đề: {row['Tiêu đề']}\nMô tả gốc: {mo_ta}\n\n"

    prompt += """
TRẢ VỀ JSON THUẦN (không markdown):
{
  "insight": "...",
  "ket_qua": [{"id": 0, "tom_tat": "..."}]
}
"""
    print(f"  Đang tóm tắt {ten_nguon} với Gemini...")
    ket_qua = goi_gemini(prompt)

    if ket_qua and "ket_qua" in ket_qua:
        map_tt = {item["id"]: item["tom_tat"] for item in ket_qua["ket_qua"]}
        df["Tóm tắt AI"] = df["ID"].map(map_tt).fillna("Không đủ dữ liệu để tóm tắt.")
    else:
        df["Tóm tắt AI"] = "Lỗi xử lý API."

    return df


def lay_tin_cafef_cafebiz():
    df_cafef = lay_tin_cafef(8)
    time.sleep(1)
    df_cafebiz = lay_tin_cafebiz(8)

    df_cafef = tom_tat_voi_ai(df_cafef, "CafeF")
    time.sleep(3)
    df_cafebiz = tom_tat_voi_ai(df_cafebiz, "CafeBiz")

    if not df_cafef.empty:
        duong_dan = os.path.join(WORKDIR, "timeline_cafef_loc_tin.csv")
        df_cafef.to_csv(duong_dan, index=False, sep=";", encoding="utf-8-sig")
        print(f"  -> Đã lưu {duong_dan}")
    if not df_cafebiz.empty:
        duong_dan = os.path.join(WORKDIR, "cafebiz_tin_moi.csv")
        df_cafebiz.to_csv(duong_dan, index=False, sep=";", encoding="utf-8-sig")
        print(f"  -> Đã lưu {duong_dan}")

    return df_cafef, df_cafebiz


# ======================================================================
# 4. MEDIASTACK
# ======================================================================
def lay_tin_mediastack():
    print("\n[4/5] Đang lấy tin từ Mediastack...")
    if not MEDIA_STACK_KEY:
        print("  ⚠️ Thiếu MEDIA_STACK_API_KEY, bỏ qua nguồn Mediastack.")
        return pd.DataFrame()

    url_api = "http://api.mediastack.com/v1/news"
    params = {
        "access_key": MEDIA_STACK_KEY,
        "categories": "business",
        "languages": "en",
        "countries": "us,gb",
        "limit": 10,
        "sort": "published_desc",
    }

    danh_sach_tin = []
    try:
        response = requests.get(url_api, params=params, timeout=10)
        if response.status_code == 200:
            data_json = response.json()
            bai_viet = data_json.get("data", [])
            print(f"  -> Tải về {len(bai_viet)} bản tin Mediastack.")
            for idx, item in enumerate(bai_viet):
                raw_time = item.get("published_at", "")
                try:
                    thoi_gian_chuan = pd.to_datetime(raw_time).strftime("%d/%m/%Y %H:%M")
                except Exception:
                    thoi_gian_chuan = raw_time

                tieu_de_goc = (item.get("title") or "Không có tiêu đề").strip()
                nguon_bao = (item.get("source") or "Báo Quốc Tế").capitalize()
                mo_ta = item.get("description", "Không có mô tả")
                link_goc = item.get("url", "#")

                danh_sach_tin.append(
                    {
                        "ID": idx,
                        "Thời gian": thoi_gian_chuan,
                        "Tiêu đề Gốc": tieu_de_goc,
                        "Nguồn": nguon_bao,
                        "Mô tả Anh": mo_ta,
                        "Link": link_goc,
                    }
                )
        else:
            print(f"  ❌ Lỗi API Mediastack: {response.status_code}")
    except Exception as e:
        print(f"  ❌ Lỗi mạng: {e}")

    if not danh_sach_tin:
        return pd.DataFrame()

    prompt = (
        "Bạn là Giám đốc Phân tích Vĩ mô. Dưới đây là danh sách tin tức tài chính quốc tế bằng tiếng Anh.\n"
        "Nhiệm vụ của bạn:\n"
        "1. Đọc Tiêu đề và Mô tả tiếng Anh của từng bài.\n"
        "2. Dịch ý chính và viết 1 đoạn tóm tắt (khoảng 2-3 câu) bằng TIẾNG VIỆT cho mỗi bài.\n"
        "3. Văn phong báo chí tài chính chuyên nghiệp.\n\n"
    )
    for tin in danh_sach_tin:
        prompt += f"ID: {tin['ID']}\nTitle: {tin['Tiêu đề Gốc']}\nDescription: {tin['Mô tả Anh']}\n\n"
    prompt += """
TRẢ VỀ KẾT QUẢ THEO ĐÚNG CẤU TRÚC JSON SAU:
{
  "ket_qua": [
    {"id": 0, "tom_tat_vn": "Bản dịch tóm tắt tiếng Việt 1..."}
  ]
}
"""
    ket_qua_json = goi_gemini(prompt)
    if ket_qua_json and "ket_qua" in ket_qua_json:
        map_tom_tat = {}
        for item in ket_qua_json["ket_qua"]:
            tin_id = item.get("id", item.get("ID"))
            tin_tom_tat = item.get(
                "tom_tat_vn", item.get("tom_tat", item.get("tom_tat_VN", item.get("tóm_tắt", "Không thể dịch.")))
            )
            map_tom_tat[tin_id] = tin_tom_tat
        for tin in danh_sach_tin:
            tin["Tóm tắt AI"] = map_tom_tat.get(tin["ID"], "Không thể dịch và tóm tắt.")
    else:
        for tin in danh_sach_tin:
            tin["Tóm tắt AI"] = "Lỗi xử lý AI đa ngôn ngữ."

    df = pd.DataFrame(danh_sach_tin)
    df_export = df[["Thời gian", "Tiêu đề Gốc", "Tóm tắt AI", "Link"]].rename(columns={"Tiêu đề Gốc": "Tiêu đề bài báo"})
    duong_dan = os.path.join(WORKDIR, "mediastack_tin_quoc_te.csv")
    df_export.to_csv(duong_dan, index=False, sep=";", encoding="utf-8-sig")
    print(f"  -> Đã lưu {duong_dan}")
    return df_export


# ======================================================================
# 5. DỰNG BÁO CÁO HTML -> XUẤT PDF
# ======================================================================
def xuat_bao_cao_pdf(df_trong_nuoc, df_cafef, df_cafebiz, df_quoc_te, df_mediastack):
    print("\n[5/5] Đang dựng báo cáo và xuất PDF...")
    from weasyprint import HTML

    thoi_gian_vn_hien_tai = pd.Timestamp.now("Asia/Ho_Chi_Minh")
    ngay_xuat_file = thoi_gian_vn_hien_tai.strftime("%d_%m_%Y")
    gio_phut_giay = thoi_gian_vn_hien_tai.strftime("%H%M%S")
    gio_hien_thi_footer = thoi_gian_vn_hien_tai.strftime("%H:%M ngày %d/%m/%Y")

    ten_file_pdf = f"Cap_nhat_Tin_tuc_ngay_{ngay_xuat_file}_{gio_phut_giay}.pdf"
    duong_dan_luu_pdf = os.path.join(WORKDIR, ten_file_pdf)

    css_style = """
<style>
    body { font-family: 'Times New Roman', 'Symbola', serif; font-size: 10pt; color: #1e293b; padding: 20px; line-height: 1.4; }
    h1 { text-align: center; color: #0f172a; border-bottom: 3px solid #1e293b; padding-bottom: 10px; margin-bottom: 10px; font-size: 18pt; font-weight: bold; }
    .section-header { text-align: center; font-size: 16pt; font-weight: bold; margin-top: 40px; margin-bottom: 20px; padding-bottom: 5px; }
    .header-trong-nuoc { color: #1e3a8a; border-bottom: 2px dashed #1e3a8a; }
    .header-quoc-te { color: #0f766e; border-bottom: 2px dashed #0f766e; page-break-before: always; }
    h2 { font-family: 'Times New Roman', 'Symbola', serif; color: #fff; padding: 8px 15px; border-radius: 4px; margin-top: 30px; margin-bottom: 5px; font-size: 12pt; font-weight: bold; }
    .bg-trong-nuoc { background-color: #1e3a8a; }
    .bg-cafef      { background-color: #991b1b; }
    .bg-cafebiz    { background-color: #c2410c; }
    .bg-quoc-te    { background-color: #0f766e; }
    .bg-mediastack { background-color: #4c1d95; }
    table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 10px; border-top: 1px solid #64748b; border-left: 1px solid #64748b; }
    tbody { break-inside: avoid !important; page-break-inside: avoid !important; }
    tr, td, th { break-inside: avoid !important; }
    th { background-color: #f1f5f9; padding: 7px 10px; border-bottom: 1px solid #64748b; border-right: 1px solid #64748b; text-align: center; font-weight: bold; font-size: 10pt; color: #0f172a; }
    td { padding: 7px 10px; border-bottom: 1px solid #64748b; border-right: 1px solid #64748b; vertical-align: top; text-align: justify; font-size: 10pt; }
    .col-time { width: 12%; font-weight: bold; text-align: center; }
    .col-title { width: 33%; font-weight: bold; }
    .col-summary { width: 55%; }
    .footer { text-align: right; margin-top: 50px; font-size: 10pt; color: #64748b; font-style: italic; }
    @page {
        margin-bottom: 2cm;
        @bottom-center {
            content: "© Bản quyền thuộc về FTU-kudo";
            font-family: 'Times New Roman', serif;
            font-size: 8pt;
            color: #94a3b8;
        }
    }
</style>
"""

    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    {css_style}
</head>
<body>
    <h1>BÁO CÁO PHÂN TÍCH TIN TỨC THỊ TRƯỜNG</h1>
"""

    # PHẦN I: TRONG NƯỚC
    if not df_trong_nuoc.empty or not df_cafef.empty or not df_cafebiz.empty:
        html_content += "<div class='section-header header-trong-nuoc'>PHẦN I: THỊ TRƯỜNG TRONG NƯỚC</div>"

    if not df_trong_nuoc.empty:
        html_content += "<h2 class='bg-trong-nuoc'>ĐIỂM TIN VĨ MÔ & DOANH NGHIỆP</h2>"
        html_content += "<table><thead><tr><th class='col-time'>Thời gian</th><th class='col-title'>Tiêu đề & Chuyên mục</th><th class='col-summary'>Tóm tắt Insight</th></tr></thead>"
        for _, row in df_trong_nuoc.iterrows():
            tieu_de = row.get("Tiêu đề gốc", row.get("Tiêu đề", "Không có tiêu đề"))
            parts = tieu_de.rsplit(" - ", 1)
            if len(parts) == 2:
                tieu_de = f"{parts[0]} - <i><b>{parts[1]}</b></i>"

            tom_tat = row.get("Tóm tắt AI (Đã xác minh)", row.get("Tóm tắt AI", "Không có tóm tắt"))
            link_goc = row.get("Link", "#")

            chuyen_muc = row.get("Chuyên mục", "")
          
            if chuyen_muc == "Kinh tế Vĩ mô":
                tag_html = f"<div style='background-color: #dcfce3; color: #16a34a; padding: 3px 6px; border-radius: 3px; font-size: 8pt; font-weight: bold; display: inline-block; margin-bottom: 4px;'>{chuyen_muc}</div><br>"
            elif chuyen_muc == "Tin Cập nhật":
                tag_html = f"<div style='background-color: #e0e7ff; color: #4f46e5; padding: 3px 6px; border-radius: 3px; font-size: 8pt; font-weight: bold; display: inline-block; margin-bottom: 4px;'>{chuyen_muc}</div><br>"
            elif chuyen_muc == "Tin Thời sự":
                tag_html = f"<div style='background-color: #fee2e2; color: #ef4444; padding: 3px 6px; border-radius: 3px; font-size: 8pt; font-weight: bold; display: inline-block; margin-bottom: 4px;'>{chuyen_muc}</div><br>"
            else:
                tag_html = ""
            html_content += f"<tbody><tr><td class='col-time'>{row['Thời gian']}</td><td class='col-title'>{tag_html}<a href='{link_goc}' style='color: inherit; text-decoration: none;'>{tieu_de}</a></td><td class='col-summary'>{tom_tat}</td></tr></tbody>"
        html_content += "</table>"

    if not df_cafef.empty:
        html_content += "<h2 class='bg-cafef'>TIMELINE CAFEF: NHỊP ĐẬP THỊ TRƯỜNG</h2>"
        html_content += "<table><thead><tr><th class='col-time'>Thời gian</th><th class='col-title'>Tiêu đề Bài báo</th><th class='col-summary'>Tóm tắt Insight</th></tr></thead>"
        for _, row in df_cafef.iterrows():
            tieu_de = str(row.get("Tiêu đề", row.get("Tiêu đề Bài báo", "Không có tiêu đề")))
            parts = tieu_de.rsplit(" - ", 1)
            if len(parts) == 2:
                tieu_de = f"{parts[0]} - <i><b>{parts[1]}</b></i>"

            tom_tat = str(row.get("Tóm tắt AI", row.get("Tóm tắt (Đã kiểm chứng bởi AI)", "Không có tóm tắt")))
            link_goc = str(row.get("Link", "#"))

            html_content += f"<tbody><tr><td class='col-time'>{row['Thời gian']}</td><td class='col-title'><a href='{link_goc}' style='color: inherit; text-decoration: none;'>{tieu_de}</a></td><td class='col-summary'>{tom_tat}</td></tr></tbody>"
        html_content += "</table>"

    if not df_cafebiz.empty:
        html_content += "<h2 class='bg-cafebiz'>TIMELINE CAFEBIZ: TIN TÀI CHÍNH ĐÃ LỌC</h2>"
        html_content += "<table><thead><tr><th class='col-time'>Thời gian</th><th class='col-title'>Tiêu đề Bài báo</th><th class='col-summary'>Tóm tắt Insight</th></tr></thead>"
        for _, row in df_cafebiz.iterrows():
            tieu_de = str(row.get("Tiêu đề bài báo", row.get("Tiêu đề", "Không có tiêu đề")))
            parts = tieu_de.rsplit(" - ", 1)
            if len(parts) == 2:
                tieu_de = f"{parts[0]} - <i><b>{parts[1]}</b></i>"

            tom_tat = str(
                row.get("Tóm tắt AI", row.get("Tóm tắt Insight (Bởi AI)", row.get("Tóm tắt nhanh (AI)", "Không có tóm tắt.")))
            )
            link_goc = str(row.get("Link", "#"))

            html_content += f"<tbody><tr><td class='col-time'>{row['Thời gian']}</td><td class='col-title'><a href='{link_goc}' style='color: inherit; text-decoration: none;'>{tieu_de}</a></td><td class='col-summary'>{tom_tat}</td></tr></tbody>"
        html_content += "</table>"

    # PHẦN II: QUỐC TẾ
    if not df_quoc_te.empty or not df_mediastack.empty:
        html_content += "<div class='section-header header-quoc-te'>PHẦN II: THỊ TRƯỜNG QUỐC TẾ</div>"

    if not df_quoc_te.empty:
        html_content += "<h2 class='bg-quoc-te'>ĐIỂM TIN VĨ MÔ TOÀN CẦU</h2>"
        html_content += "<table><thead><tr><th class='col-time'>Thời gian (Giờ VN)</th><th class='col-title'>Tiêu đề (Gốc) & Chuyên mục</th><th class='col-summary'>Tóm tắt Insight</th></tr></thead>"
        for _, row in df_quoc_te.iterrows():
            tieu_de = row.get("Tiêu đề gốc", row.get("Tiêu đề", "Không có tiêu đề"))
            parts = tieu_de.rsplit(" - ", 1)
            if len(parts) == 2:
                tieu_de = f"{parts[0]} - <i><b>{parts[1]}</b></i>"

            tom_tat = row.get("Tóm tắt AI (Đã xác minh)", row.get("Tóm tắt AI", "Không có tóm tắt"))
            link_goc = row.get("Link", "#")

            chuyen_muc = row.get("Chuyên mục", "")
            if chuyen_muc == "Tin Nổi Bật Toàn Cầu":
                tag_html = f"<div style='background-color: #f3e8ff; color: #7e22ce; padding: 3px 6px; border-radius: 3px; font-size: 8pt; font-weight: bold; display: inline-block; margin-bottom: 4px;'>{chuyen_muc}</div><br>"
            elif chuyen_muc == "Doanh Nghiệp Quốc Tế":
                tag_html = f"<div style='background-color: #e0f2fe; color: #0369a1; padding: 3px 6px; border-radius: 3px; font-size: 8pt; font-weight: bold; display: inline-block; margin-bottom: 4px;'>{chuyen_muc}</div><br>"
            elif chuyen_muc == "Vĩ Mô & Phố Wall":
                tag_html = f"<div style='background-color: #ccfbf1; color: #0f766e; padding: 3px 6px; border-radius: 3px; font-size: 8pt; font-weight: bold; display: inline-block; margin-bottom: 4px;'>{chuyen_muc}</div><br>"
            else:
                tag_html = ""

            html_content += f"<tbody><tr><td class='col-time'>{row['Thời gian']}</td><td class='col-title'>{tag_html}<a href='{link_goc}' style='color: inherit; text-decoration: none;'>{tieu_de}</a></td><td class='col-summary'>{tom_tat}</td></tr></tbody>"
        html_content += "</table>"

    if not df_mediastack.empty:
        html_content += "<h2 class='bg-mediastack'>DỮ LIỆU TÀI CHÍNH TOÀN CẦU (MEDIASTACK)</h2>"
        html_content += "<table><thead><tr><th class='col-time'>Thời gian</th><th class='col-title'>Tiêu đề Bài báo</th><th class='col-summary'>Tóm tắt Insight</th></tr></thead>"
        for _, row in df_mediastack.iterrows():
            tieu_de = str(row.get("Tiêu đề bài báo", "Không có tiêu đề"))
            parts = tieu_de.rsplit(" - ", 1)
            if len(parts) == 2:
                tieu_de = f"{parts[0]} - <i><b>{parts[1]}</b></i>"

            tom_tat = str(row.get("Tóm tắt AI", row.get("Mô tả", "Không có tóm tắt.")))
            link_goc = str(row.get("Link", "#"))

            html_content += f"<tbody><tr><td class='col-time'>{row['Thời gian']}</td><td class='col-title'><a href='{link_goc}' style='color: inherit; text-decoration: none;'>{tieu_de}</a></td><td class='col-summary'>{tom_tat}</td></tr></tbody>"
        html_content += "</table>"

    html_content += f"""
    <div class="footer">Báo cáo được tổng hợp và xuất tự động vào lúc {gio_hien_thi_footer}</div>
</body>
</html>
"""

    HTML(string=html_content).write_pdf(duong_dan_luu_pdf)
    print(f"  ✅ Xuất PDF thành công: {duong_dan_luu_pdf}")
    return duong_dan_luu_pdf, gio_hien_thi_footer


# ======================================================================
# 6. UPLOAD PDF LÊN GOOGLE DRIVE (Service Account)
# ======================================================================
def upload_len_drive(duong_dan_pdf):
    sa_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    folder_id = os.environ.get("GDRIVE_FOLDER_ID")

    if not sa_json or not folder_id:
        print("\n⚠️ Thiếu GDRIVE_SERVICE_ACCOUNT_JSON hoặc GDRIVE_FOLDER_ID -> Bỏ qua bước lưu Google Drive.")
        return

    print("\nĐang upload báo cáo lên Google Drive...")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds)

        file_metadata = {
            "name": os.path.basename(duong_dan_pdf),
            "parents": [folder_id],
        }
        media = MediaFileUpload(duong_dan_pdf, mimetype="application/pdf")
        file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
        print(f"  ✅ Đã lưu vào Google Drive (file id: {file.get('id')}).")
    except Exception as e:
        print(f"  ❌ Lỗi khi upload Google Drive: {e}")


# ======================================================================
# 7. GỬI EMAIL KÈM PDF CHO KHÁCH HÀNG (Gmail SMTP)
# ======================================================================
def gui_email(duong_dan_pdf, gio_hien_thi_footer):
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_app_password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient_emails = os.environ.get("RECIPIENT_EMAILS", "")

    if not gmail_address or not gmail_app_password or not recipient_emails:
        print("\n⚠️ Thiếu GMAIL_ADDRESS / GMAIL_APP_PASSWORD / RECIPIENT_EMAILS -> Bỏ qua bước gửi email.")
        return

    danh_sach_nhan = [e.strip() for e in recipient_emails.split(",") if e.strip()]
    if not danh_sach_nhan:
        print("\n⚠️ Danh sách email người nhận trống -> Bỏ qua bước gửi email.")
        return

    print(f"\nĐang gửi email báo cáo đến {len(danh_sach_nhan)} người nhận...")

    msg = EmailMessage()
    msg["Subject"] = f"Cập nhật Tin tức Thị trường - {gio_hien_thi_footer}"
    msg["From"] = gmail_address
    msg["To"] = gmail_address  # gửi cho chính mình ở To, khách hàng nằm ở Bcc để bảo mật email của nhau
    msg["Bcc"] = ", ".join(danh_sach_nhan)
    msg.set_content(
        "Kính chào Quý khách,\n\n"
        "Đính kèm là Báo cáo Phân tích Tin tức Thị trường được tổng hợp tự động trong ngày hôm nay.\n\n"
        "Trân trọng,\nFTU-kudo."
    )

    mime_type, _ = mimetypes.guess_type(duong_dan_pdf)
    maintype, subtype = (mime_type or "application/pdf").split("/", 1)
    with open(duong_dan_pdf, "rb") as f:
        msg.add_attachment(
            f.read(), maintype=maintype, subtype=subtype, filename=os.path.basename(duong_dan_pdf)
        )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_address, gmail_app_password)
            smtp.send_message(msg)
        print("  ✅ Đã gửi email thành công.")
    except Exception as e:
        print(f"  ❌ Lỗi khi gửi email: {e}")


# ======================================================================
# MAIN
# ======================================================================
def doc_csv_an_toan(ten_file):
    """Đọc lại 1 file CSV đã lưu ở Bước 1. Trả về DataFrame trống nếu file không tồn tại
    (do nguồn đó hôm nay không có bài nào), và thay mọi giá trị trống/NaN bằng chuỗi rỗng
    để không bị hiện chữ 'nan' trong PDF."""
    duong_dan = os.path.join(WORKDIR, ten_file)
    if not os.path.exists(duong_dan):
        return pd.DataFrame()
    df = pd.read_csv(duong_dan, sep=";", encoding="utf-8-sig")
    return df.fillna("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build", action="store_true",
        help="Chỉ lấy tin và tóm tắt AI, lưu ra các file CSV — KHÔNG xuất PDF, KHÔNG gửi email.",
    )
    parser.add_argument(
        "--send-email", action="store_true",
        help="Đọc lại CSV đã lưu từ --build, xuất PDF NGAY LÚC NÀY rồi gửi email ngay sau đó.",
    )
    args = parser.parse_args()

    # Chế độ 2: đọc lại 5 file CSV đã lưu ở Bước 1 -> xuất PDF (đúng lúc này) -> gửi email ngay
    if args.send_email:
        df_trong_nuoc = doc_csv_an_toan("tin_trong_nuoc_rss_chuan.csv")
        df_quoc_te = doc_csv_an_toan("tin_quoc_te_rss_chuan.csv")
        df_cafef = doc_csv_an_toan("timeline_cafef_loc_tin.csv")
        df_cafebiz = doc_csv_an_toan("cafebiz_tin_moi.csv")
        df_mediastack = doc_csv_an_toan("mediastack_tin_quoc_te.csv")

        duong_dan_pdf, gio_hien_thi_footer = xuat_bao_cao_pdf(
            df_trong_nuoc, df_cafef, df_cafebiz, df_quoc_te, df_mediastack
        )
        gui_email(duong_dan_pdf, gio_hien_thi_footer)
        print("\n🎉 ĐÃ XUẤT PDF VÀ GỬI EMAIL.")
        return

    # Chế độ 1 (--build) hoặc chạy đầy đủ như cũ (không truyền cờ gì):
    # các hàm dưới đây tự lưu CSV ra đĩa như một phần xử lý của chúng.
    df_trong_nuoc = lay_tin_trong_nuoc()
    df_quoc_te = lay_tin_quoc_te()
    df_cafef, df_cafebiz = lay_tin_cafef_cafebiz()
    df_mediastack = lay_tin_mediastack()

    if args.build:
        print("\n✅ Đã lấy tin và tóm tắt AI xong, dữ liệu đã lưu vào các file CSV. "
              "Chạy `python main.py --send-email` để xuất PDF và gửi email.")
        return

    # Đã bỏ bước lưu Google Drive: Service Account không có dung lượng lưu trữ riêng
    # (lỗi storageQuotaExceeded) — PDF vẫn được gửi đầy đủ qua email.
    duong_dan_pdf, gio_hien_thi_footer = xuat_bao_cao_pdf(
        df_trong_nuoc, df_cafef, df_cafebiz, df_quoc_te, df_mediastack
    )
    gui_email(duong_dan_pdf, gio_hien_thi_footer)
    print("\n🎉 HOÀN TẤT TOÀN BỘ QUY TRÌNH.")


if __name__ == "__main__":
    main()

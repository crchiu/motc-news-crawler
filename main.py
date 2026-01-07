import os
import re
import time
import argparse
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import requests
from bs4 import BeautifulSoup


LIST_URL = "https://www.motc.gov.tw/ch/app/news_list?lang=ch&folderName=ch&id=14"
BASE_URL = "https://www.motc.gov.tw"
OUT_DIR_DEFAULT = "data"


@dataclass
class NewsItem:
    url: str
    date: str
    unit: str
    title: str


def sanitize_filename(name: str, max_len: int = 180) -> str:
    # Windows / macOS / Linux 通用檔名清理
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(". ")
    if len(name) > max_len:
        name = name[:max_len].rstrip()
    return name


def build_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; motc-press-downloader/1.0; +https://www.motc.gov.tw/)",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        }
    )
    return s


def fetch_html(session: requests.Session, url: str, timeout: int = 30, retries: int = 3) -> str:
    last_err = None
    for _ in range(retries):
        try:
            r = session.get(url, timeout=timeout)
            r.raise_for_status()
            if not r.encoding:
                r.encoding = r.apparent_encoding
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(1.0)
    raise RuntimeError(f"Fetch failed after retries: {url}\n{last_err}")


def set_query_param(url: str, key: str, value: str) -> str:
    u = urlparse(url)
    q = parse_qs(u.query, keep_blank_values=True)
    q[key] = [value]
    new_query = urlencode(q, doseq=True)
    return urlunparse((u.scheme, u.netloc, u.path, u.params, new_query, u.fragment))


def parse_list_page(html: str) -> List[NewsItem]:
    """
    解析新聞稿列表頁：取得每則新聞的 date/unit/title/url
    """
    soup = BeautifulSoup(html, "lxml")

    anchors = soup.select(
        'a[href*="/ch/app/news_list/view"][href*="module=news"][href*="serno="][href*="id=14"]'
    )

    items: List[NewsItem] = []
    for a in anchors:
        text = a.get_text(" ", strip=True)
        if "發布日期：" not in text or "發布單位：" not in text:
            continue

        m_date = re.search(r"發布日期：\s*([0-9]{3}-[0-9]{2}-[0-9]{2})", text)
        m_unit = re.search(r"發布單位：\s*([^\s]+)", text)
        if not m_date or not m_unit:
            continue

        date = m_date.group(1)
        unit = m_unit.group(1)

        title = re.sub(r"^.*?發布單位：\s*[^\s]+\s*", "", text).strip()
        if not title:
            continue

        url = urljoin(BASE_URL, (a.get("href") or "").strip())
        items.append(NewsItem(url=url, date=date, unit=unit, title=title))

    # 以 URL 去重
    uniq: Dict[str, NewsItem] = {}
    for it in items:
        uniq[it.url] = it
    return list(uniq.values())


def extract_main_text_block(soup: BeautifulSoup) -> List[str]:
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n")]
    lines = [ln for ln in lines if ln]

    idxs = [i for i, ln in enumerate(lines) if ln == "交通新聞稿"]
    start = idxs[-1] if idxs else 0
    return lines[start:]


def parse_article_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    block = extract_main_text_block(soup)

    def find_value(prefix: str) -> Optional[str]:
        for ln in block[:80]:
            if ln.startswith(prefix):
                return ln.split("：", 1)[-1].strip()
        return None

    news_type = find_value("新聞類別")
    biz_type = find_value("業務分類") or find_value("分類")
    date = find_value("發布日期")
    unit = find_value("發布單位")

    # 標題：通常位於「發布單位：xxx」後面一行
    title = None
    for i, ln in enumerate(block[:120]):
        if ln.startswith("發布單位："):
            for j in range(i + 1, min(i + 10, len(block))):
                cand = block[j].strip()
                if not cand:
                    continue
                if "：" in cand and any(
                    cand.startswith(p) for p in ["新聞類別", "業務分類", "分類", "發布日期", "發布單位"]
                ):
                    continue
                title = cand
                break
            break

    # 正文：標題之後
    body_lines: List[str] = []
    if title and title in block:
        t_idx = block.index(title)
        body_lines = block[t_idx + 1 :]
    else:
        body_lines = block[10:]

    STOP_MARKERS = {"回上一頁", "回頁首", "更新日期", "瀏覽人次", "點閱次數", "分享"}
    cleaned: List[str] = []
    for ln in body_lines:
        if ln in STOP_MARKERS:
            break
        cleaned.append(ln)

    return {
        "url": url,
        "news_type": news_type,
        "biz_type": biz_type,
        "date": date,
        "unit": unit,
        "title": title,
        "body_lines": cleaned,
    }


def to_markdown(article: dict) -> str:
    title = article.get("title") or "(未解析到標題)"
    md = []
    md.append(f"# {title}")
    md.append("")
    md.append(f"- 發布日期：{article.get('date') or ''}")
    md.append(f"- 發布單位：{article.get('unit') or ''}")
    if article.get("news_type"):
        md.append(f"- 新聞類別：{article.get('news_type')}")
    if article.get("biz_type"):
        md.append(f"- 業務分類：{article.get('biz_type')}")
    md.append(f"- 原文連結：{article.get('url')}")
    md.append("")
    md.append("---")
    md.append("")

    for ln in article.get("body_lines", []):
        md.append(ln)

    md.append("")
    return "\n".join(md)


def atomic_write(path: str, content: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def target_path(out_dir: str, unit: str, date: str, title: str) -> str:
    filename = sanitize_filename(f"{unit}_{date}_{title}.md")
    return os.path.join(out_dir, filename)


def discover_pagination_mode(
    session: requests.Session,
    base_url: str,
    first_page_items: List[NewsItem],
    sleep: float,
) -> Tuple[str, str, int, bool]:
    """
    回傳：(mode, param_name, step, offset_one_based)
    - mode: "page" 或 "offset"
    - param_name: 例如 "page"
    - step: offset 模式使用，通常等於每頁筆數
    - offset_one_based: offset 是否採 1-based（例如 start=16）或 0-based（start=15）
    """
    if not first_page_items:
        raise RuntimeError("第一頁未解析到任何新聞，無法偵測分頁參數。")

    # 用 URL 集合比較是否真的翻到不同頁
    first_urls = {it.url for it in first_page_items}
    page_size = max(1, len(first_page_items))

    # 常見 page 參數
    page_params = ["page", "pageIndex", "pageNo", "pageNum", "p", "pg"]
    for p in page_params:
        test_url = set_query_param(base_url, p, "2")
        html = fetch_html(session, test_url)
        items = parse_list_page(html)
        urls = {it.url for it in items}
        if items and urls != first_urls:
            # 成功翻頁
            return ("page", p, 0, False)
        time.sleep(sleep)

    # 常見 offset 參數（以每頁筆數推估 step）
    offset_params = ["start", "offset", "from", "begin"]
    for p in offset_params:
        # 先試 0-based：第二頁起點=page_size
        for one_based in (False, True):
            val = page_size + 1 if one_based else page_size
            test_url = set_query_param(base_url, p, str(val))
            html = fetch_html(session, test_url)
            items = parse_list_page(html)
            urls = {it.url for it in items}
            if items and urls != first_urls:
                return ("offset", p, page_size, one_based)
            time.sleep(sleep)

    raise RuntimeError(
        "無法自動偵測分頁方式（可能該站分頁不是用 GET 參數）。"
        "若你遇到此錯誤，把抓到的列表頁 HTML（或其中 pagination 區塊）貼我，我再幫你改成對應的 POST/表單分頁。"
    )


def iter_list_pages(
    session: requests.Session,
    base_url: str,
    sleep: float,
    max_pages: int = 0,
):
    """
    產生器：逐頁 yield List[NewsItem]
    - max_pages=0 表示不限
    """
    page_no = 0
    html1 = fetch_html(session, base_url)
    items1 = parse_list_page(html1)
    yield (page_no, base_url, items1)

    if max_pages == 1:
        return

    mode, param, step, offset_one_based = discover_pagination_mode(session, base_url, items1, sleep)

    while True:
        page_no += 1
        if max_pages and page_no > max_pages:
            return

        if mode == "page":
            url = set_query_param(base_url, param, str(page_no))
        else:
            # offset: 第 N 頁的起點
            offset = (page_no - 1) * step
            offset = offset + 1 if offset_one_based else offset
            url = set_query_param(base_url, param, str(offset))

        html = fetch_html(session, url)
        items = parse_list_page(html)

        # 終止條件：該頁無內容（可能到最末頁）
        if not items:
            return

        yield (page_no, url, items)

        time.sleep(sleep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-url", default=LIST_URL)
    ap.add_argument("--out-dir", default=OUT_DIR_DEFAULT)
    ap.add_argument("--sleep", type=float, default=0.5, help="每次請求間隔秒數（避免對站台造成壓力）")
    ap.add_argument("--max-pages", type=int, default=0, help="最多抓幾頁（0=不限，用於測試）")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    session = build_session()

    total_saved = 0
    total_seen = 0

    for page_no, page_url, items in iter_list_pages(session, args.list_url, args.sleep, args.max_pages):
        print(f"\n[PAGE {page_no}] {page_url}")
        print(f"[INFO] 本頁 {len(items)} 則")

        for idx, item in enumerate(items, 1):
            total_seen += 1

            # 先算檔名，再決定要不要停
            out_path = target_path(args.out_dir, item.unit, item.date, item.title)
            if os.path.exists(out_path):
                print(f"[STOP] 已存在：{os.path.basename(out_path)}")
                print("       視為該日期以前的新聞已下載完成，停止整體下載流程。")
                print(f"\n[DONE] 本次新增 {total_saved} 篇；掃描 {total_seen} 篇後停止。")
                print(f"       輸出目錄：{os.path.abspath(args.out_dir)}")
                return

            print(f"[{idx}/{len(items)}] 下載：{item.date} | {item.unit} | {item.title}")

            try:
                article_html = fetch_html(session, item.url)
                article = parse_article_page(article_html, item.url)

                # 若內頁沒解析到就用列表資訊補齊
                date = article.get("date") or item.date
                unit = article.get("unit") or item.unit
                title = article.get("title") or item.title

                out_path = target_path(args.out_dir, unit, date, title)

                article["date"] = date
                article["unit"] = unit
                article["title"] = title

                md = to_markdown(article)
                atomic_write(out_path, md)

                total_saved += 1

                time.sleep(args.sleep)

            except Exception as e:
                print(f"[ERROR] 下載失敗：{item.url}\n  {e}")

    print(f"\n[DONE] 已抓到最末頁或無更多內容。")
    print(f"       本次新增 {total_saved} 篇；共掃描 {total_seen} 篇。")
    print(f"       輸出目錄：{os.path.abspath(args.out_dir)}")


if __name__ == "__main__":
    main()

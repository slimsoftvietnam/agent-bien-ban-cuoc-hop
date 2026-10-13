"""Agent Biên bản họp — dòng lệnh chính.

  python mm.py doctor                                   kiểm tra máy đã đủ công cụ chưa
  python mm.py prepare  --input <file> [--input <file2>] --participants <ds.csv> --out <thư mục> [--title ..] [--date YYYY-MM-DD]
  python mm.py validate --out <thư mục>                 kiểm chứng minutes.json (Claude viết)
  python mm.py render   --out <thư mục> [--no-open]     xuất HTML/PDF/Excel/email
  python mm.py set-email --out <thư mục> --name "Họ tên" --email a@b.com
  python mm.py mark-sent --out <thư mục> --name "Họ tên" --message-id <id>
  python mm.py selftest                                 tự kiểm thử với dữ liệu mẫu
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mmlib import (EMAIL_RE, MODELS, AgentError, find_browser, find_ffmpeg, log, read_json, slugify,  # noqa: E402
                   write_json)


def default_out(args) -> Path:
    base = Path.cwd() / "bien-ban"
    name = args.title or (Path(args.input[0]).stem if args.input else "cuoc-hop")
    stamp = args.date or time.strftime("%Y-%m-%d")
    return base / f"{stamp}-{slugify(name, 40)}"


def cmd_doctor(_args) -> int:
    ok = True
    log("Kiểm tra môi trường Agent Biên bản họp")
    log(f"  {'✅' if sys.version_info >= (3, 10) else '❌'} Python {sys.version.split()[0]}")
    for mod, why, required in [("openpyxl", "xuất Excel", True), ("PIL", "xử lý ảnh chụp video", True),
                               ("numpy", "xử lý âm thanh", True), ("faster_whisper", "chuyển ghi âm thành chữ", False),
                               ("sherpa_onnx", "nhận diện người nói theo giọng", False)]:
        has = importlib.util.find_spec(mod) is not None
        ok &= has or not required
        log(f"  {'✅' if has else ('❌' if required else '⚠ ')} {mod:<15} ({why}){'' if has else ' — chạy setup.ps1'}")
    ff = find_ffmpeg()
    log(f"  {'✅' if ff else '⚠ '} FFmpeg ({'đọc audio/video'}){'' if ff else ' — winget install Gyan.FFmpeg'}")
    br = find_browser()
    ok &= bool(br)
    log(f"  {'✅' if br else '❌'} Trình duyệt Edge/Chrome (xuất PDF){'' if br else ' — cài Microsoft Edge hoặc Chrome'}")
    models = (MODELS / "speaker-embedding.onnx").exists() and (MODELS / "sherpa-onnx-pyannote-segmentation-3-0" / "model.int8.onnx").exists()
    log(f"  {'✅' if models else '⚠ '} Model nhận diện giọng nói{'' if models else ' — chạy setup.ps1 để tải'}")
    log("")
    log("✅ Sẵn sàng." if ok else "❌ Còn thiếu công cụ bắt buộc — chạy setup.ps1.")
    return 0 if ok else 1


def cmd_prepare(args) -> int:
    from prepare import prepare
    out = Path(args.out) if args.out else default_out(args)
    log(f"📁 Thư mục biên bản: {out}")
    prepare(args.input, out, args.participants, args.title or "", args.date or "", args.speakers, args.model,
            keep_audio=args.keep_audio)
    return 0


def cmd_validate(args) -> int:
    from validate import validate
    return 0 if validate(Path(args.out))["ok"] else 1


def cmd_render(args) -> int:
    from render import render
    render(Path(args.out), open_after=not args.no_open, only_emails=args.only_emails, minutes_link=args.minutes_link or "",
           layout=args.layout, password=args.password or "")
    return 0


def cmd_set_email(args) -> int:
    from render import render
    from validate import validate
    out = Path(args.out)
    email = args.email.strip()
    if not EMAIL_RE.fullmatch(email):
        raise AgentError(f"Địa chỉ email không hợp lệ: {email}")
    f = out / "work" / "participants.json"
    ps = read_json(f)
    hit = next((p for p in ps if p["name"] == args.name), None)
    if hit:
        hit["email"], hit["email_valid"] = email, True
    else:
        ps.append({"name": args.name, "email": email, "role": "", "aliases": [], "email_valid": True})
    write_json(f, ps)
    log(f"✅ Đã cập nhật email {args.name} → {email}")
    if (out / "minutes.json").exists() and validate(out)["ok"]:
        render(out, open_after=False, only_emails=True)
    return 0


def cmd_mark_sent(args) -> int:
    from emails import mark_sent
    mark_sent(Path(args.out), args.name, args.message_id, args.status)
    log(f"✅ Đã ghi nhận: {args.name} — {args.status} ({args.message_id})")
    return 0


def cmd_selftest(args) -> int:
    from selftest import run_selftest
    return run_selftest(skip_media=args.quick, base=Path(args.out) if args.out else None)


def main() -> int:
    ap = argparse.ArgumentParser(description="Agent Biên bản cuộc họp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    p = sub.add_parser("prepare")
    p.add_argument("--input", action="append", required=True, help="transcript / audio / video (có thể lặp lại)")
    p.add_argument("--participants", help="danh sách người tham gia (CSV/XLSX/JSON/TXT)")
    p.add_argument("--out")
    p.add_argument("--title")
    p.add_argument("--date", help="ngày họp YYYY-MM-DD (chỉ điền khi người dùng cung cấp)")
    p.add_argument("--speakers", type=int, help="số người nói (nếu biết) để tách giọng chính xác hơn")
    p.add_argument("--model", help="model Whisper: small | medium | large-v3-turbo")
    p.add_argument("--keep-audio", action="store_true")
    v = sub.add_parser("validate")
    v.add_argument("--out", required=True)
    r = sub.add_parser("render")
    r.add_argument("--out", required=True)
    r.add_argument("--no-open", action="store_true")
    r.add_argument("--only-emails", action="store_true")
    r.add_argument("--minutes-link", help="link Google Drive của biên bản để chèn vào email")
    r.add_argument("--password", help="khoá trình đọc web bằng mật khẩu (nội dung được mã hoá AES-GCM)")
    r.add_argument("--layout", choices=["compact", "ebook"], help="compact = gọn, tối đa max_pages trang (mặc định); ebook = bản dài có bìa")
    s = sub.add_parser("set-email")
    s.add_argument("--out", required=True)
    s.add_argument("--name", required=True)
    s.add_argument("--email", required=True)
    k = sub.add_parser("mark-sent")
    k.add_argument("--out", required=True)
    k.add_argument("--name", required=True)
    k.add_argument("--message-id", required=True)
    k.add_argument("--status", default="đã gửi")
    t = sub.add_parser("selftest")
    t.add_argument("--quick", action="store_true", help="chỉ kiểm thử transcript (bỏ audio/video)")
    t.add_argument("--out", help="thư mục lưu kết quả kiểm thử")
    args = ap.parse_args()
    fn = {"doctor": cmd_doctor, "prepare": cmd_prepare, "validate": cmd_validate, "render": cmd_render,
          "set-email": cmd_set_email, "mark-sent": cmd_mark_sent, "selftest": cmd_selftest}[args.cmd]
    try:
        return fn(args)
    except AgentError as e:
        log(f"\n❌ Lỗi: {e}")
        if e.hint:
            log(f"👉 Cách xử lý: {e.hint}")
        return 2
    except KeyboardInterrupt:
        log("\n⏹ Đã dừng.")
        return 130
    except Exception as e:  # lỗi bất ngờ → ghi log chi tiết, báo ngắn gọn
        logf = Path.cwd() / "bien-ban-loi.log"
        logf.write_text(traceback.format_exc(), encoding="utf-8")
        log(f"\n❌ Lỗi không mong muốn: {type(e).__name__}: {e}\n   Chi tiết đã lưu tại {logf}")
        return 3


if __name__ == "__main__":
    sys.exit(main())

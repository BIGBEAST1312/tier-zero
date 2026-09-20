"""Generate a QR code and a printable poster for the survey.

    python scripts/make_qr.py https://forms.gle/YOUR-REAL-LINK

Produces, in docs/qr/:
    survey-qr.png       the code on its own, transparent-friendly white background
    survey-poster.png   A5 poster for printing or posting
    survey-poster.pdf   the same, print-ready

Error correction is set to H (about 30% recoverable), so the code still scans with
the logo mark in the middle and survives being printed small or slightly crumpled.

Always scan the result with your own phone before printing fifty of them.
"""

import argparse
import sys
from pathlib import Path

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_H
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("pip install 'qrcode[pil]'")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "qr"

GREEN = (18, 61, 42)
INK = (29, 33, 31)
MUTED = (107, 111, 106)
PAPER = (250, 248, 244)
MINT = (47, 158, 111)


def load_font(size, bold=False):
    """Fall back through the fonts likely to exist on a Linux box, then to
    PIL's default rather than crashing."""
    candidates = [
        "/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/crosextra/Carlito-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_qr(url: str, box: int = 16) -> Image.Image:
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H,
                       box_size=box, border=3)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=GREEN, back_color="white").convert("RGB")
    return stamp_logo(img)


def stamp_logo(img: Image.Image) -> Image.Image:
    """Put the bracket mark in the middle. Safe because error correction H
    recovers roughly 30% of the code."""
    w, h = img.size
    size = int(w * 0.20)
    badge = Image.new("RGB", (size, size), "white")
    d = ImageDraw.Draw(badge)
    pad = int(size * 0.08)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=int(size * 0.22), fill=GREEN)
    # brackets + dot, scaled to the badge
    s = size
    lw = max(2, int(s * 0.055))
    for x0, x1 in [(0.26, 0.38), (0.74, 0.62)]:
        d.line([(s * x1, s * 0.30), (s * x0, s * 0.30)], fill="white", width=lw)
        d.line([(s * x0, s * 0.30), (s * x0, s * 0.70)], fill="white", width=lw)
        d.line([(s * x0, s * 0.70), (s * x1, s * 0.70)], fill="white", width=lw)
    r = int(s * 0.085)
    d.ellipse([s / 2 - r, s / 2 - r, s / 2 + r, s / 2 + r], fill=MINT)
    img.paste(badge, ((w - size) // 2, (h - size) // 2))
    return img


def wrap(draw, text, font, max_w):
    """Word-wrap, falling back to character-wrap for anything too long to break
    on a space — a full Google Forms URL is one unbroken 'word' and will run off
    the page otherwise."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
            continue
        if cur:
            lines.append(cur)
            cur = ""
        while draw.textlength(word, font=font) > max_w:
            cut = len(word)
            while cut > 1 and draw.textlength(word[:cut], font=font) > max_w:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        cur = word
    if cur:
        lines.append(cur)
    return lines


def make_poster(qr_img: Image.Image, url: str, prize: str = "") -> Image.Image:
    # A4 at 200 dpi. Everything below is proportional to this, so changing the
    # page size alone would break the layout — the margins and type sizes are
    # scaled with it.
    W, H = 1654, 2339
    poster = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(poster)

    f_kicker = load_font(42)
    f_head = load_font(108, bold=True)
    f_body = load_font(48)
    f_small = load_font(34)
    f_url = load_font(31)

    m = 128
    y = 175

    d.text((m, y), "TIER ZERO \u00b7 A STUDENT PROJECT", font=f_kicker, fill=MINT)
    y += 80

    for line in wrap(d, "How do you get IT problems sorted?", f_head, W - 2 * m):
        d.text((m, y), line, font=f_head, fill=INK)
        y += 125

    y += 36
    body = ("We're USask students building a tool that answers IT questions from the "
            "knowledge base \u2014 so you don't open a ticket for something already "
            "documented. Tell us whether that's a real problem.")
    for line in wrap(d, body, f_body, W - 2 * m):
        d.text((m, y), line, font=f_body, fill=(74, 79, 75))
        y += 65

    y += 44
    d.rounded_rectangle([m, y, W - m, y + 106], radius=20, fill=GREEN)
    d.text((m + 40, y + 28), "5 questions  \u00b7  1 minute  \u00b7  anonymous",
           font=f_body, fill="white")
    y += 132
    if prize:
        d.rounded_rectangle([m, y, W - m, y + 94], radius=20, fill="#E4F1EE")
        d.text((m + 40, y + 24), prize, font=f_body, fill=GREEN)
        y += 138
    else:
        y += 44

    # QR
    qr_size = 760
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    qx = (W - qr_size) // 2
    d.rounded_rectangle([qx - 36, y - 36, qx + qr_size + 36, y + qr_size + 36],
                        radius=28, fill="white", outline=(224, 221, 212), width=3)
    poster.paste(qr_img, (qx, y))
    y += qr_size + 88

    d.text((m, y), "Scan with your phone camera", font=f_body, fill=INK)
    y += 72
    shown = url if len(url) <= 90 else url[:88] + "\u2026"
    for line in wrap(d, shown, f_url, W - 2 * m):
        d.text((m, y), line, font=f_url, fill=MUTED)
        y += 44

    y = H - 215
    d.line([(m, y), (W - m, y)], fill=(224, 221, 212), width=3)
    y += 34
    foot = ("A student project by Team 8, We'll Study It Later. Not affiliated with, "
            "endorsed by or sponsored by the University of Saskatchewan or Bose. The "
            "survey collects no personal information; prize draw entry is a separate "
            "optional form.")
    for line in wrap(d, foot, f_small, W - 2 * m):
        d.text((m, y), line, font=f_small, fill=MUTED)
        y += 44

    return poster



def make_card(qr_img: Image.Image, url: str, prize: str = "") -> Image.Image:
    """One quarter-page card, A6 at 200 dpi.

    A desk card is read from about arm's length and competes with whatever else
    is on the desk, so it carries a hook, the code, and nothing else. The prize
    sits under the survey line rather than above it: a card that leads with free
    headphones reads as advertising and gets binned, which is the opposite of
    what we want.
    """
    W, H = 827, 1169
    card = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(card)

    f_kicker = load_font(21)
    f_head = load_font(54, bold=True)
    f_body = load_font(26)
    f_small = load_font(18)

    m = 62
    y = 70

    d.text((m, y), "TIER ZERO \u00b7 A STUDENT PROJECT", font=f_kicker, fill=MINT)
    y += 44

    for line in wrap(d, "How do you get IT problems sorted?", f_head, W - 2 * m):
        d.text((m, y), line, font=f_head, fill=INK)
        y += 64

    y += 14
    body = ("A 1 minute survey for a USask course project. "
            "Anonymous \u2014 no name, no email, no NSID.")
    for line in wrap(d, body, f_body, W - 2 * m):
        d.text((m, y), line, font=f_body, fill=(74, 79, 75))
        y += 36

    y += 18
    d.rounded_rectangle([m, y, W - m, y + 58], radius=12, fill=GREEN)
    d.text((m + 22, y + 15), "5 questions  \u00b7  1 minute", font=f_body, fill="white")
    y += 74

    if prize:
        d.rounded_rectangle([m, y, W - m, y + 52], radius=12, fill="#E4F1EE")
        d.text((m + 22, y + 12), prize, font=f_body, fill=GREEN)
        y += 70
    else:
        y += 10

    qr_size = 400
    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS)
    qx = (W - qr_size) // 2
    d.rounded_rectangle([qx - 20, y - 20, qx + qr_size + 20, y + qr_size + 20],
                        radius=18, fill="white", outline=(224, 221, 212), width=2)
    card.paste(qr_img, (qx, y))
    y += qr_size + 44

    d.text((m, y), "Scan with your phone camera", font=f_body, fill=INK)

    y = H - 118
    d.line([(m, y), (W - m, y)], fill=(224, 221, 212), width=2)
    y += 20
    foot = ("Team 8, We'll Study It Later. Not affiliated with, endorsed by or "
            "sponsored by the University of Saskatchewan or Bose.")
    for line in wrap(d, foot, f_small, W - 2 * m):
        d.text((m, y), line, font=f_small, fill=MUTED)
        y += 26

    return card


def make_card_sheet(card: Image.Image) -> Image.Image:
    """Four cards on one A4 sheet, with hairline cut guides."""
    W, H = 1654, 2339
    sheet = Image.new("RGB", (W, H), "white")
    card = card.resize((W // 2, H // 2), Image.LANCZOS)
    for cx in (0, W // 2):
        for cy in (0, H // 2):
            sheet.paste(card, (cx, cy))
    d = ImageDraw.Draw(sheet)
    guide = (200, 200, 200)
    d.line([(W // 2, 0), (W // 2, H)], fill=guide, width=1)
    d.line([(0, H // 2), (W, H // 2)], fill=guide, width=1)
    return sheet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="the survey link, e.g. https://forms.gle/abc123")
    ap.add_argument("--outdir", default=str(OUT))
    ap.add_argument("--prize", default="",
                    help='optional prize line, e.g. "Prize draw: Bose headphones"')
    ap.add_argument("--cards", action="store_true",
                    help="also write quarter-page desk cards, four to an A4 sheet")
    args = ap.parse_args()

    if not args.url.startswith(("http://", "https://")):
        sys.exit("URL must start with http:// or https://")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    qr = make_qr(args.url)
    qr.save(outdir / "survey-qr.png")

    poster = make_poster(qr, args.url, args.prize)
    poster.save(outdir / "survey-poster.png")
    poster.save(outdir / "survey-poster.pdf", "PDF", resolution=200.0)

    print(f"wrote {outdir}/survey-qr.png")
    print(f"wrote {outdir}/survey-poster.png")
    print(f"wrote {outdir}/survey-poster.pdf")

    if args.cards:
        card = make_card(qr, args.url, args.prize)
        card.save(outdir / "survey-card.png")
        sheet = make_card_sheet(card)
        sheet.save(outdir / "survey-cards-a4.png")
        sheet.save(outdir / "survey-cards-a4.pdf", "PDF", resolution=200.0)
        print(f"wrote {outdir}/survey-card.png")
        print(f"wrote {outdir}/survey-cards-a4.pdf  (4 per sheet, cut on the guides)")

    print("\nScan it with your own phone before printing any.")


if __name__ == "__main__":
    main()

"""Generate OpenGraph social sharing images for MultAI docs.

Renders an HTML template via Playwright (headless Chromium) and saves
1200×630 PNG files to docs/assets/og/.

Usage:
    python scripts/generate_og_image.py
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

DOCS_DIR = Path(__file__).parent.parent / "docs"
OUT_DIR = DOCS_DIR / "assets" / "og"

# ── Template ──────────────────────────────────────────────────────────────────

def build_html(
    title: str,
    subtitle: str,
    tag: str = "Claude Code / Cowork Plugin",
    platforms=None,
) -> str:
    if platforms is None:
        platforms = ["Claude.ai", "ChatGPT", "Copilot", "Perplexity", "Grok", "DeepSeek", "Gemini"]

    pills_html = "".join(
        f'<span class="pill">{p}</span>' for p in platforms
    )

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap" rel="stylesheet">
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:1200px;height:630px;overflow:hidden;font-family:'Inter',system-ui,sans-serif;background:#08080f}}
  .card{{
    width:1200px;height:630px;
    background:linear-gradient(135deg,#0a0a1a 0%,#0f0f2e 45%,#150a2a 100%);
    position:relative;overflow:hidden;
    display:flex;flex-direction:column;justify-content:center;
    padding:72px 80px;
  }}
  /* decorative blobs */
  .blob1{{
    position:absolute;top:-180px;right:-140px;
    width:520px;height:520px;border-radius:50%;
    background:radial-gradient(circle,rgba(99,102,241,.22) 0%,transparent 70%);
  }}
  .blob2{{
    position:absolute;bottom:-200px;left:-100px;
    width:480px;height:480px;border-radius:50%;
    background:radial-gradient(circle,rgba(167,139,250,.14) 0%,transparent 70%);
  }}
  .blob3{{
    position:absolute;top:50%;right:80px;transform:translateY(-50%);
    width:260px;height:260px;border-radius:50%;
    background:radial-gradient(circle,rgba(236,72,153,.08) 0%,transparent 70%);
  }}
  /* grid lines */
  .grid-lines{{
    position:absolute;inset:0;
    background-image:
      linear-gradient(rgba(99,102,241,.06) 1px,transparent 1px),
      linear-gradient(90deg,rgba(99,102,241,.06) 1px,transparent 1px);
    background-size:60px 60px;
  }}
  .content{{position:relative;z-index:1}}
  .tag{{
    display:inline-flex;align-items:center;gap:8px;
    background:rgba(99,102,241,.15);
    border:1px solid rgba(99,102,241,.35);
    border-radius:999px;padding:6px 18px;
    font-size:14px;font-weight:600;letter-spacing:.04em;
    color:#818cf8;margin-bottom:28px;
  }}
  .dot{{width:7px;height:7px;border-radius:50%;background:#34d399;flex-shrink:0}}
  .logo{{
    font-size:64px;font-weight:900;letter-spacing:-.04em;
    background:linear-gradient(135deg,#818cf8 0%,#a78bfa 50%,#f472b6 100%);
    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
    margin-bottom:16px;line-height:1;
  }}
  .title{{
    font-size:38px;font-weight:800;letter-spacing:-.03em;
    color:#e2e8f0;line-height:1.2;margin-bottom:20px;
    max-width:820px;
  }}
  .subtitle{{
    font-size:20px;color:#64748b;line-height:1.6;
    max-width:680px;margin-bottom:40px;
  }}
  .pills{{display:flex;gap:10px;flex-wrap:wrap}}
  .pill{{
    padding:6px 14px;border-radius:999px;
    border:1px solid rgba(99,102,241,.25);
    background:rgba(99,102,241,.08);
    font-size:13px;font-weight:500;color:#94a3b8;
  }}
  /* bottom bar */
  .bar{{
    position:absolute;bottom:0;left:0;right:0;height:3px;
    background:linear-gradient(90deg,#4f46e5,#7c3aed,#db2777);
  }}
</style>
</head>
<body>
<div class="card">
  <div class="blob1"></div>
  <div class="blob2"></div>
  <div class="blob3"></div>
  <div class="grid-lines"></div>
  <div class="content">
    <div class="tag"><span class="dot"></span>{tag}</div>
    <div class="logo">MultAI</div>
    <div class="title">{title}</div>
    <div class="subtitle">{subtitle}</div>
    <div class="pills">{pills_html}</div>
  </div>
  <div class="bar"></div>
</div>
</body>
</html>"""


# ── Variants ──────────────────────────────────────────────────────────────────

VARIANTS = [
    {
        "slug": "og-main",
        "title": "Leverage 7 Leading AIs at Once",
        "subtitle": "Submit one prompt to Claude.ai, ChatGPT, Copilot, Perplexity, Grok, DeepSeek & Gemini simultaneously — from Claude Code or Cowork.",
        "tag": "Claude Code / Cowork Plugin",
    },
    {
        "slug": "og-help",
        "title": "Help Center",
        "subtitle": "Everything you need — from first install to running all 7 platforms simultaneously.",
        "tag": "Documentation",
        "platforms": ["Quick Start", "Core Concepts", "Reference", "Troubleshooting"],
    },
]


# ── Renderer ──────────────────────────────────────────────────────────────────

async def render(variant: dict) -> Path:
    html = build_html(
        title=variant["title"],
        subtitle=variant["subtitle"],
        tag=variant.get("tag", "MultAI"),
        platforms=variant.get("platforms"),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = OUT_DIR / f"{variant['slug']}.html"
    png_path = OUT_DIR / f"{variant['slug']}.png"

    html_path.write_text(html, encoding="utf-8")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 630})
        await page.goto(f"file://{html_path.resolve()}", wait_until="networkidle")
        await page.screenshot(path=str(png_path), clip={"x": 0, "y": 0, "width": 1200, "height": 630})
        await browser.close()

    html_path.unlink()  # remove temp HTML
    print(f"  ✓ {png_path.relative_to(DOCS_DIR.parent)}")
    return png_path


async def main() -> None:
    print("Generating OG images…")
    for v in VARIANTS:
        await render(v)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
